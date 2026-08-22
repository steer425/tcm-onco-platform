"""新聞內文 → 平台實體比對（藥材 / 成分 / 靶點 / 疾病）。

目的：讓讀者從新聞直接點進查詢站，把「新聞情報」接回
「中藥 → 成分 → 靶點 → 疾病」的關聯網絡。

比對策略（刻意保守，寧可漏抓也不要誤連）：
  * 拉丁字母詞：以「詞」為單位做 1~4 連字詞比對，需完整詞界，
    並套用停用詞表；長度過短或過於通用的詞一律不建索引。
  * 中日韓字詞：以 2~8 字的滑動視窗比對（中文沒有詞界可用）。
  * 基因/靶點符號（如 AKT1、TP53）：大小寫敏感 + 完整詞界，
    否則 "AKT1" 會誤中一堆無關字串。
  * 成分（29,384 筆）預設只索引「夠獨特」的分子名，
    避免 water / glucose 這類通用字把每篇新聞都連上。

效能：用「詞典查表 + n-gram」而不是 29k 詞的正規表示式聯集——
後者光編譯就要數秒，且比對是線性掃描。查表法對每篇文章只需 O(字數×視窗)。
索引一次收集流程只建一次，之後重複使用。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 停用詞：這些字串太通用，若拿來當實體名稱會把幾乎每篇新聞都連上
# ---------------------------------------------------------------------------
GENERIC_STOPWORDS = {
    # 通用名詞
    "water", "acid", "oil", "extract", "powder", "root", "leaf", "seed", "fruit",
    "flower", "bark", "stem", "herb", "herbs", "plant", "plants", "compound",
    "protein", "receptor", "enzyme", "factor", "kinase", "gene", "genes",
    "cell", "cells", "human", "mouse", "rat", "study", "trial", "patient",
    "patients", "cancer", "tumor", "tumour", "disease", "diseases", "syndrome",
    "carcinoma", "neoplasm", "neoplasms", "therapy", "treatment", "control",
    "group", "effect", "effects", "activity", "analysis", "review", "report",
    "alcohol", "sugar", "glucose", "sucrose", "starch", "protein", "vitamin",
    "calcium", "sodium", "potassium", "iron", "zinc", "copper",
    # 中文通用
    "中藥", "中医", "中醫", "藥材", "药材", "腫瘤", "肿瘤", "癌症", "疾病",
    "細胞", "细胞", "蛋白", "基因", "治療", "治疗", "研究", "患者", "病人",
    "作用", "效果", "分析", "報告", "报告",
}

# 拉丁詞最短長度（含）；短於此不建索引
MIN_LATIN_LEN = 5
# 中日韓字詞最短長度（含）
MIN_CJK_LEN = 2
# 中日韓比對視窗上限
MAX_CJK_WINDOW = 8
# 拉丁 n-gram 上限（幾個「詞」）
MAX_LATIN_NGRAM = 4

_CJK_RE = re.compile(r"[一-鿿]")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-']*")
# 基因/靶點符號：2~10 碼，全大寫或大寫+數字，例如 TP53、AKT1、PIK3CA、HIF1A
_GENE_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


@dataclass(frozen=True)
class EntityRef:
    entity_type: str        # herb / ingredient / target / disease
    entity_key: str         # 主鍵的字串形式
    display_name: str
    match_type: str         # exact_cn / exact_en / pinyin / gene_symbol
    herb_id: int | None = None
    mol_id: str | None = None
    tar_id: str | None = None
    dis_id: str | None = None


@dataclass
class EntityHit:
    ref: EntityRef
    matched_text: str


def _has_cjk(s: str) -> bool:
    return bool(_CJK_RE.search(s))


def _normalize_latin(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


class EntityIndex:
    """實體名稱 → EntityRef 的查表索引。建一次、重複使用。"""

    def __init__(self) -> None:
        self.latin: dict[str, EntityRef] = {}      # 小寫正規化後的拉丁名稱
        self.cjk: dict[str, EntityRef] = {}        # 原樣中日韓名稱
        self.gene_symbols: dict[str, EntityRef] = {}  # 大小寫敏感的基因符號
        self._max_cjk_len = MIN_CJK_LEN

    # -- 建索引 ---------------------------------------------------------
    def add(self, name: str | None, ref: EntityRef) -> None:
        if not name:
            return
        name = name.strip()
        if not name:
            return

        if _has_cjk(name):
            if len(name) < MIN_CJK_LEN or name in GENERIC_STOPWORDS:
                return
            # 中文名稱過長時比對視窗吃不到，直接跳過（這類名稱通常也不會出現在新聞標題）
            if len(name) > MAX_CJK_WINDOW:
                return
            self.cjk.setdefault(name, ref)
            self._max_cjk_len = max(self._max_cjk_len, len(name))
            return

        # 基因/靶點符號：保留原始大小寫，另存一份
        if _GENE_SYMBOL_RE.match(name):
            self.gene_symbols.setdefault(name, ref)
            return

        norm = _normalize_latin(name)
        if len(norm) < MIN_LATIN_LEN or norm in GENERIC_STOPWORDS:
            return
        # 詞數超過上限的名稱比對不到，不浪費記憶體
        if len(norm.split(" ")) > MAX_LATIN_NGRAM:
            return
        self.latin.setdefault(norm, ref)

    @property
    def size(self) -> int:
        return len(self.latin) + len(self.cjk) + len(self.gene_symbols)

    # -- 比對 -----------------------------------------------------------
    def find(self, text: str, limit: int = 24) -> list[EntityHit]:
        if not text:
            return []

        hits: dict[tuple[str, str], EntityHit] = {}

        # 1) 基因/靶點符號：大小寫敏感 + 完整詞界
        if self.gene_symbols:
            for token in set(re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", text)):
                ref = self.gene_symbols.get(token)
                if ref:
                    hits.setdefault((ref.entity_type, ref.entity_key),
                                    EntityHit(ref=ref, matched_text=token))

        # 2) 拉丁 n-gram
        if self.latin:
            tokens = _LATIN_TOKEN_RE.findall(text)
            lowered = [t.lower() for t in tokens]
            n = len(lowered)
            for i in range(n):
                for size in range(1, MAX_LATIN_NGRAM + 1):
                    if i + size > n:
                        break
                    gram = " ".join(lowered[i:i + size])
                    if len(gram) < MIN_LATIN_LEN:
                        continue
                    ref = self.latin.get(gram)
                    if ref:
                        hits.setdefault((ref.entity_type, ref.entity_key),
                                        EntityHit(ref=ref,
                                                  matched_text=" ".join(tokens[i:i + size])))

        # 3) 中日韓滑動視窗
        if self.cjk:
            cjk_only = "".join(ch if _CJK_RE.match(ch) else "\n" for ch in text)
            for segment in cjk_only.split("\n"):
                seg_len = len(segment)
                if seg_len < MIN_CJK_LEN:
                    continue
                for i in range(seg_len):
                    for size in range(MIN_CJK_LEN, min(self._max_cjk_len, seg_len - i) + 1):
                        gram = segment[i:i + size]
                        ref = self.cjk.get(gram)
                        if ref:
                            hits.setdefault((ref.entity_type, ref.entity_key),
                                            EntityHit(ref=ref, matched_text=gram))

        out = list(hits.values())
        # 名稱越長代表越具體，優先保留
        out.sort(key=lambda h: -len(h.matched_text))
        return out[:limit]


# ---------------------------------------------------------------------------
# 從資料庫建索引
# ---------------------------------------------------------------------------
def build_index(db, *, include_ingredients: bool = True) -> EntityIndex:
    """從 TCMSP 主檔建立比對索引。

    include_ingredients=False 可關掉成分比對（成分有 29k 筆，
    名稱同名衝突較多，若發現誤連可先關掉）。
    """
    from app import models

    idx = EntityIndex()

    # ---- 藥材（499 筆）----
    herbs = db.query(
        models.TcmspHerb.id,
        models.TcmspHerb.herb_cn_name,
        models.TcmspHerb.herb_pinyin,
        models.TcmspHerb.herb_en_name,
        models.TcmspHerb.child_cn_name,
        models.TcmspHerb.child_en_name,
    ).filter(models.TcmspHerb.status == "active").all()

    for h in herbs:
        display = h.herb_cn_name or h.herb_en_name or str(h.id)
        base = dict(entity_type="herb", entity_key=str(h.id),
                    display_name=display, herb_id=h.id)
        idx.add(h.herb_cn_name, EntityRef(**base, match_type="exact_cn"))
        idx.add(h.child_cn_name, EntityRef(**base, match_type="exact_cn"))
        idx.add(h.herb_en_name, EntityRef(**base, match_type="exact_en"))
        idx.add(h.child_en_name, EntityRef(**base, match_type="exact_en"))
        idx.add(h.herb_pinyin, EntityRef(**base, match_type="pinyin"))

    # ---- 靶點（3,311 筆）----
    targets = db.query(
        models.TcmspTarget.tar_id, models.TcmspTarget.target_name,
    ).all()
    for t in targets:
        if not t.target_name:
            continue
        ref = EntityRef(entity_type="target", entity_key=t.tar_id,
                        display_name=t.target_name, tar_id=t.tar_id,
                        match_type="gene_symbol" if _GENE_SYMBOL_RE.match(t.target_name.strip())
                        else "exact_en")
        idx.add(t.target_name, ref)

    # ---- 疾病（837 筆）----
    diseases = db.query(
        models.TcmspDisease.dis_id,
        models.TcmspDisease.disease_name,
        models.TcmspDisease.disease_cn_name,
    ).all()
    for d in diseases:
        display = d.disease_cn_name or d.disease_name or d.dis_id
        base = dict(entity_type="disease", entity_key=d.dis_id,
                    display_name=display, dis_id=d.dis_id)
        idx.add(d.disease_cn_name, EntityRef(**base, match_type="exact_cn"))
        idx.add(d.disease_name, EntityRef(**base, match_type="exact_en"))

    # ---- 成分（29,384 筆，選用）----
    if include_ingredients:
        ingredients = db.query(
            models.TcmspIngredient.mol_id, models.TcmspIngredient.molecule_name,
        ).all()
        for ing in ingredients:
            if not ing.molecule_name:
                continue
            name = ing.molecule_name.strip()
            # 成分名稱門檻更嚴：太短或純數字/代號的不建索引
            if len(name) < 6 or name.isdigit():
                continue
            idx.add(name, EntityRef(entity_type="ingredient", entity_key=ing.mol_id,
                                    display_name=name, mol_id=ing.mol_id,
                                    match_type="exact_en"))

    logger.info("實體索引建立完成：latin=%s cjk=%s gene=%s（共 %s 筆）",
                len(idx.latin), len(idx.cjk), len(idx.gene_symbols), idx.size)
    return idx


def article_text(title: str, title_zh: str | None,
                 abstract: str | None, summary_zh: str | None) -> str:
    """組出要拿去比對的文字。摘要截斷避免長文拖慢比對。"""
    parts: Iterable[str | None] = (title, title_zh, (abstract or "")[:3000], summary_zh)
    return "\n".join(p for p in parts if p)
