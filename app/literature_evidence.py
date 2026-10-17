"""Step 5 PubMed 文獻證據分級：把文獻綁到「藥材—活性成分—靶點」組合。

分析鏈路第五站的另一半。Step 6（`app/depmap_analysis.py`）回答「這味藥打得到的靶點裡，
哪些是腫瘤細胞株選擇性依賴的」；這裡回答「這些組合在文獻裡有沒有人做過、做到什麼程度」。

## 查詢單位

一次查詢 ＝ 一個（藥材, 基因符號）。基因來自 Step 6 通過選擇性門檻的那一份清單
（`depmap_analysis.select_herb_targets()` 的 `gated`，**同一個函式**，不另寫篩選）；
藥材端的詞是藥材名稱＋打到這個靶點的**活性成分**名稱。

## 這裡的「證據等級」量的是什麼

`level` 是**研究設計**（統合分析 > 臨床試驗 > 人體觀察 > 動物 > 細胞 > 計算預測；綜述另列），
**不是**「這篇證明了成分作用於這個靶點」。PubMed 命中只代表三組詞共同出現——
規格 C 的 tier 4「文獻共現」。所以另外給兩個讀文獻的線索：

* `comention`：同一句話裡同時提到藥材／成分與靶點（sentence），還是摘要裡各自提到（abstract），
  還是文字裡都找不到、只靠 PubMed 索引（MeSH 等）命中（index_only）。
* `direction`：共現句裡靶點附近的作用方向字詞（下調／上調）。**啟發式**，只提醒不下結論。
  BCL2 文件列的「作用方向」缺口：CRISPR 依賴要轉成治療假說，前提是化合物**抑制**該靶點。

## 循環論證（`circular`）

網絡藥理學論文的靶點清單大多就是從 TCMSP 撈出來的，跟本平台同源。
這類論文**不能**當成支持 TCMSP 註記的獨立證據——拿它來佐證，等於用 TCMSP 證明 TCMSP。
有濕實驗驗證的仍保留原本的設計層級，但一律帶 `circular` 旗標；只有計算的，層級就是 computational。

## 不做的事

* 不讀全文、不判斷結論正負（「無效」的研究同樣會被計入）。
* 不把成分層級的命中算成藥材的證據：槲皮素、山柰酚這類廣泛存在的成分，
  文獻多半跟這味藥無關。`matched_entities` 會分開記 herb／ingredient，畫面也分開呈現。
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from app import depmap_analysis as dm, models
from app.news.collectors.pubmed import _parse_pub_date, _text

logger = logging.getLogger(__name__)

GRADING_VERSION = "1"

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
TOOL = "grace-tcm-literature"

RETMAX = 30                 # 每組合最多抓回幾篇（依相關度排序）；命中總數另記
MAX_INGREDIENT_TERMS = 12   # 查詢式裡最多放幾個成分名
MIN_TERM_LEN = 4            # 太短的名稱會撈到一堆無關的東西

# ---------------------------------------------------------------------------
# 研究設計層級
# ---------------------------------------------------------------------------
LEVELS = {
    # 代碼: (排序, 中文標籤)
    "meta":          (1, "系統性回顧／統合分析"),
    "trial":         (2, "臨床試驗"),
    "human_obs":     (3, "人體觀察研究"),
    "animal":        (4, "動物實驗"),
    "cell":          (5, "細胞實驗"),
    "computational": (6, "計算預測"),
    "review":        (7, "綜述"),
    "unknown":       (8, "未判定"),
}

_META_TYPES = {"meta-analysis", "systematic review"}
_TRIAL_TYPES = {"randomized controlled trial", "controlled clinical trial", "clinical trial",
                "clinical trial, phase i", "clinical trial, phase ii", "clinical trial, phase iii",
                "clinical trial, phase iv", "pragmatic clinical trial"}
_OBS_TYPES = {"observational study", "case reports", "multicenter study"}

# 文字線索（小寫比對）。人體觀察刻意不收 "patients"——細胞論文的背景句幾乎都有
# 「for patients with ...」，收了會把一半的細胞實驗升成人體研究。
_META_CUES = ("meta-analysis", "systematic review")
_TRIAL_CUES = ("randomized controlled", "randomised controlled", "double-blind", "placebo-controlled")
_OBS_CUES = ("cohort", "retrospective", "case-control", "case report", "participants were enrolled",
             "patients were enrolled", "tissue samples from patients")
_ANIMAL_CUES = ("xenograft", "nude mice", "mice", "mouse model", " rats", "rat model",
                "in vivo", "zebrafish", "tumor-bearing", "tumour-bearing")
_CELL_CUES = ("cell line", "in vitro", " cells", "cck-8", "mtt assay", "colony formation",
              "western blot", "flow cytometry")
_COMPUTE_CUES = ("network pharmacology", "molecular docking", "in silico", "bioinformatic",
                 "molecular dynamics", "virtual screening")
_CIRCULAR_CUES = ("network pharmacology", "tcmsp")

# 方向線索：取靶點所在子句裡**離靶點最近**的方向字。整句一起算，「誘導凋亡、下調 BCL2」
# 會變成混合；「BCL2 下降、BAX 上升」也會。刻意不收 induce／promote——
# 摘要裡幾乎都是「induce apoptosis」「promote cell death」，跟靶點的方向無關。
_DOWN_CUES = ("inhibit", "suppress", "downregulat", "down-regulat", "decreas", "reduc",
              "attenuat", "block", "diminish", "lower", "silenc", "knockdown")
_UP_CUES = ("upregulat", "up-regulat", "increas", "elevat", "activat", "enhanc", "stimulat")
_CLAUSE_SPLIT = re.compile(r",|;|\band\b|\bwhile\b|\bwhereas\b|\bbut\b", re.IGNORECASE)
_DIR_FALLBACK_BEFORE = 60   # 子句裡沒有方向字時（「inhibited the expression of X, Y and BCL2」），往前看

_GREEK = {"β": "beta", "α": "alpha", "γ": "gamma", "δ": "delta", "κ": "kappa"}


def level_label(code: str) -> str:
    return LEVELS.get(code, LEVELS["unknown"])[1]


def _norm(text: str) -> str:
    t = text or ""
    for g, w in _GREEK.items():
        t = t.replace(g, w)
    return t


def grade_design(pub_types: list[str], text: str) -> tuple[str, list[str]]:
    """回傳 (層級代碼, 旗標)。`text` 為標題＋摘要。"""
    pts = {p.lower() for p in pub_types or []}
    low = " " + _norm(text).lower()
    flags: list[str] = []

    if "retracted publication" in pts or "retraction of publication" in pts:
        flags.append("retracted")
    computational = any(c in low for c in _COMPUTE_CUES)
    if any(c in low for c in _CIRCULAR_CUES):
        flags.append("circular")

    if pts & _META_TYPES or any(c in low for c in _META_CUES):
        return "meta", flags
    # 綜述的摘要也會出現 mice、cells，所以出版類型是綜述就直接定為綜述
    if "review" in pts:
        return "review", flags
    if pts & _TRIAL_TYPES or any(c in low for c in _TRIAL_CUES):
        level = "trial"
    elif pts & _OBS_TYPES or any(c in low for c in _OBS_CUES):
        level = "human_obs"
    elif any(c in low for c in _ANIMAL_CUES):
        level = "animal"
    elif any(c in low for c in _CELL_CUES):
        level = "cell"
    elif computational:
        return "computational", flags
    else:
        return "unknown", flags
    if computational:
        flags.append("includes_computational")
    return level, flags


# ---------------------------------------------------------------------------
# 詞彙與比對
# ---------------------------------------------------------------------------
def _clean_term(name: str | None) -> str | None:
    if not name:
        return None
    t = _norm(name).replace('"', "").strip()
    if len(t) < MIN_TERM_LEN or t.replace(" ", "").isdigit():
        return None
    return t


def herb_terms(herb) -> list[str]:
    out = []
    for n in (herb.herb_en_name, herb.herb_pinyin):
        t = _clean_term(n)
        if t and t.lower() not in {o.lower() for o in out}:
            out.append(t)
    return out


def gene_terms(symbol: str, protein_name: str | None = None) -> list[str]:
    """基因符號、加連字號的寫法（BCL2 → BCL-2）、TCMSP 蛋白名稱。

    兩個字母以下的符號（AR）不放進查詢式——在 PubMed 會撈到 "AR" 這種縮寫的所有論文。
    """
    out: list[str] = []
    s = (symbol or "").strip()
    if len(s) > 2:
        out.append(s)
        m = re.match(r"^([A-Za-z]+)(\d+[A-Za-z]?)$", s)
        if m:
            out.append(f"{m.group(1)}-{m.group(2)}")
    p = _clean_term(protein_name)
    if p and p.lower() not in {o.lower() for o in out}:
        out.append(p)
    return out


CANCER_CLAUSE = ("(neoplasms[mh] OR cancer*[tiab] OR tumor*[tiab] OR tumour*[tiab] "
                 "OR carcinoma*[tiab])")


def build_query(herb_t: list[str], ingredient_t: list[str], gene_t: list[str]) -> str | None:
    entity = herb_t + [t for t in ingredient_t if t.lower() not in {h.lower() for h in herb_t}]
    if not entity or not gene_t:
        return None
    ent = " OR ".join(f'"{t}"[tiab]' for t in entity)
    gen = " OR ".join(f'"{t}"[tiab]' for t in gene_t)
    return f"({ent}) AND ({gen}) AND {CANCER_CLAUSE}"


def _term_re(term: str, case_sensitive: bool = False):
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", flags)


def _sentences(title: str, abstract: str | None) -> list[str]:
    out = [title] if title else []
    if abstract:
        # 摘要的段落標籤（BACKGROUND: ...）由收集器併成多行
        for para in abstract.split("\n"):
            out.extend(s for s in re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9(\[])", para) if s.strip())
    return out


def _nearest_cue(text: str, pos: int) -> str | None:
    """text 裡離 pos 最近的方向字，回傳 "down"／"up"／None。"""
    best, best_d = None, None
    for kind, cues in (("down", _DOWN_CUES), ("up", _UP_CUES)):
        for c in cues:
            for m in re.finditer(re.escape(c), text):
                d = abs(m.start() - pos)
                if best_d is None or d < best_d:
                    best, best_d = kind, d
    return best


def _direction(sentence: str, gene_res: list) -> str | None:
    low = sentence.lower()
    # 子句邊界
    bounds, start = [], 0
    for m in _CLAUSE_SPLIT.finditer(low):
        bounds.append((start, m.start()))
        start = m.end()
    bounds.append((start, len(low)))
    found = set()
    for gre in gene_res:
        for m in gre.finditer(sentence):
            a, b = next(((x, y) for x, y in bounds if x <= m.start() < y), (0, len(low)))
            kind = _nearest_cue(low[a:b], m.start() - a)
            if kind is None:
                lo = max(0, m.start() - _DIR_FALLBACK_BEFORE)
                kind = _nearest_cue(low[lo:m.start()], m.start() - lo)
            if kind:
                found.add(kind)
    if len(found) > 1:
        return "mixed"
    return found.pop() if found else None


def analyse_text(title: str, abstract: str | None, entities: list[dict], gene_t: list[str]) -> dict:
    """共現與方向。`entities` = [{"kind", "term", "mol_id"}]。"""
    title_n, abstract_n = _norm(title), _norm(abstract or "")
    # 三個字以下的基因詞大小寫要一致（避免 "ar"、"met" 這種一般字）
    gene_res = [_term_re(g, case_sensitive=len(g) <= 3) for g in gene_t]
    ent_res = [(e, _term_re(_norm(e["term"]))) for e in entities]
    blob = f"{title_n}\n{abstract_n}"

    matched = [e for e, r in ent_res if r.search(blob)]
    gene_hit = any(r.search(blob) for r in gene_res)

    best_sentence, direction, comention = None, None, "index_only"
    if matched and gene_hit:
        comention = "abstract"
        for s in _sentences(title_n, abstract_n):
            if any(r.search(s) for _, r in ent_res) and any(r.search(s) for r in gene_res):
                comention = "sentence"
                best_sentence = s.strip()
                direction = _direction(s, gene_res)
                break
    return {"comention": comention, "direction": direction,
            "matched": matched, "sentence": best_sentence[:600] if best_sentence else None}


# ---------------------------------------------------------------------------
# 選題：藥材 → 要查的基因（與 Step 6 共用判定）
# ---------------------------------------------------------------------------
def herb_selection(db: Session, herb_id: int, release: str, max_ratio: float = dm.DEFAULT_MAX_RATIO):
    return dm.select_herb_targets(db, herb_id, release, max_ratio)


def ingredients_for_symbol(db: Session, sel: dict, symbol: str) -> list[dict]:
    """本藥材的**活性成分**中打到這個基因的，[{mol_id, molecule_name}]。"""
    tars = [t for t, syms in sel["t2s"].items() if t in sel["tar_ids"] and symbol in syms]
    mol_ids = sel["meta"]["passed"]
    if not tars or not mol_ids:
        return []
    edges = (db.query(models.TcmspIngredientTarget.mol_id)
             .filter(models.TcmspIngredientTarget.tar_id.in_(tars),
                     models.TcmspIngredientTarget.mol_id.in_(mol_ids)).distinct().all())
    ids = {e[0] for e in edges}
    rows = (db.query(models.TcmspIngredient)
            .filter(models.TcmspIngredient.mol_id.in_(ids)).all()) if ids else []
    return sorted(({"mol_id": r.mol_id, "molecule_name": r.molecule_name} for r in rows),
                  key=lambda r: ((r["molecule_name"] or "").lower(), r["mol_id"]))


def protein_name_for_symbol(db: Session, sel: dict, symbol: str) -> str | None:
    tars = sorted(t for t, syms in sel["t2s"].items() if t in sel["tar_ids"] and symbol in syms)
    if not tars:
        return None
    t = db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id == tars[0]).first()
    return t.target_name if t else None


def collect_queue(db: Session, herb_id: int, sel: dict, refresh: bool = False,
                  genes: list[str] | None = None) -> list[str]:
    """**唯一一份**「還要查哪些基因」的判定，統計端點與批次端點共用（rules.md 4-1）。

    順序照 Step 6 畫面（通過選擇性門檻、效應量由強到弱）。
    `refresh=False` 時跳過已查過、且分級規則版本相同的；`genes` 指定時只取交集。
    """
    order = [s.gene_symbol for s in sel["gated"]]
    if genes:
        want = {g.strip().upper() for g in genes if g and g.strip()}
        order = [g for g in order if g.upper() in want]
    if refresh:
        return order
    done = {r.gene_symbol for r in db.query(models.LiteratureSearch)
            .filter(models.LiteratureSearch.herb_id == herb_id,
                    models.LiteratureSearch.status != "error",
                    models.LiteratureSearch.grading_version == GRADING_VERSION).all()}
    return [g for g in order if g not in done]


# ---------------------------------------------------------------------------
# PubMed（測試裡整支被取代）
# ---------------------------------------------------------------------------
def _params(email: str | None, api_key: str | None) -> dict:
    p = {"db": "pubmed", "tool": TOOL}
    if email:
        p["email"] = email
    if api_key:
        p["api_key"] = api_key
    return p


def esearch(client: httpx.Client, term: str, *, email=None, api_key=None, retmax=RETMAX) -> tuple[int, list[str]]:
    r = client.get(ESEARCH, params={**_params(email, api_key), "term": term, "retmode": "json",
                                    "retmax": retmax, "sort": "relevance"})
    r.raise_for_status()
    res = r.json().get("esearchresult", {})
    return int(res.get("count") or 0), list(res.get("idlist") or [])


def efetch(client: httpx.Client, pmids: list[str], *, email=None, api_key=None) -> list[dict]:
    if not pmids:
        return []
    r = client.get(EFETCH, params={**_params(email, api_key), "id": ",".join(pmids),
                                   "retmode": "xml", "rettype": "abstract"})
    r.raise_for_status()
    return parse_efetch(r.text)


def parse_efetch(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for art in root.findall(".//PubmedArticle"):
        pmid = _text(art.find(".//MedlineCitation/PMID")) or _text(art.find(".//PMID"))
        if not pmid:
            continue
        parts = []
        for ab in art.findall(".//Abstract/AbstractText"):
            body = _text(ab)
            if body:
                parts.append(f"{ab.get('Label')}: {body}" if ab.get("Label") else body)
        doi = next((a.text.strip() for a in art.findall(".//ArticleId")
                    if a.get("IdType") == "doi" and a.text), None)
        pub = _parse_pub_date(art)
        out.append({
            "pmid": pmid.strip(),
            "title": _text(art.find(".//ArticleTitle")) or f"PMID {pmid}",
            "abstract": "\n".join(parts) or None,
            "journal": _text(art.find(".//Journal/Title")),
            "year": pub.year if pub else None,
            "doi": doi,
            "pub_types": [p for p in (_text(x) for x in art.findall(".//PublicationTypeList/PublicationType")) if p],
        })
    return out


# ---------------------------------------------------------------------------
# 一個組合：查詢 → 分級 → 寫入
# ---------------------------------------------------------------------------
def collect_one(db: Session, client: httpx.Client, herb, sel: dict, symbol: str, *,
                user_id: str | None = None, email=None, api_key=None, pause: float = 0.34) -> dict:
    """回傳 {"gene_symbol", "status", "total_count", "n_fetched", "error"}。

    失敗時寫一筆 status=error（不刪舊的文章），讓畫面看得出「查過但失敗」而不是「沒查過」。
    """
    ings = ingredients_for_symbol(db, sel, symbol)
    herb_t = herb_terms(herb)
    ing_t, entities = [], [{"kind": "herb", "term": t, "mol_id": None} for t in herb_t]
    for i in ings:
        t = _clean_term(i["molecule_name"])
        if t and t.lower() not in {x.lower() for x in herb_t + ing_t}:
            ing_t.append(t)
            entities.append({"kind": "ingredient", "term": t, "mol_id": i["mol_id"]})
    ing_t = ing_t[:MAX_INGREDIENT_TERMS]
    entities = [e for e in entities if e["kind"] == "herb" or e["term"] in ing_t]
    gene_t = gene_terms(symbol, protein_name_for_symbol(db, sel, symbol))
    term = build_query(herb_t, ing_t, gene_t)

    search = (db.query(models.LiteratureSearch)
              .filter(models.LiteratureSearch.herb_id == herb.id,
                      models.LiteratureSearch.gene_symbol == symbol).first())
    if search is None:
        search = models.LiteratureSearch(herb_id=herb.id, gene_symbol=symbol, query_term=term or "")
        db.add(search)
    search.query_term = term or ""
    search.searched_by = user_id
    search.searched_at = datetime.utcnow()
    search.grading_version = GRADING_VERSION

    if not term:
        search.status, search.error = "error", "沒有可用的查詢詞（藥材名稱或基因名稱太短）"
        search.total_count = search.n_fetched = 0
        db.commit()
        return {"gene_symbol": symbol, "status": "error", "total_count": 0, "n_fetched": 0,
                "error": search.error}

    try:
        total, pmids = esearch(client, term, email=email, api_key=api_key)
        time.sleep(pause)
        arts = efetch(client, pmids, email=email, api_key=api_key) if pmids else []
        time.sleep(pause)
    except Exception as exc:  # noqa: BLE001 — 外部呼叫任何失敗都記下來，不中斷整批
        logger.warning("[literature] %s/%s 查詢失敗：%s", herb.id, symbol, exc)
        search.status, search.error = "error", f"{type(exc).__name__}: {str(exc)[:300]}"
        db.commit()
        return {"gene_symbol": symbol, "status": "error", "total_count": search.total_count or 0,
                "n_fetched": search.n_fetched or 0, "error": search.error}

    db.flush()
    db.query(models.LiteratureEvidence).filter(
        models.LiteratureEvidence.search_id == search.id).delete(synchronize_session=False)
    seen = set()
    for a in arts:
        if a["pmid"] in seen:
            continue
        seen.add(a["pmid"])
        level, flags = grade_design(a["pub_types"], f"{a['title']}\n{a['abstract'] or ''}")
        tx = analyse_text(a["title"], a["abstract"], entities, gene_t)
        db.add(models.LiteratureEvidence(
            search_id=search.id, pmid=a["pmid"], title=a["title"][:2000], journal=a["journal"],
            pub_year=a["year"], doi=a["doi"], pub_types=json.dumps(a["pub_types"], ensure_ascii=False),
            level=level, level_rank=LEVELS[level][0], comention=tx["comention"],
            direction=tx["direction"],
            matched_entities=json.dumps(tx["matched"], ensure_ascii=False),
            evidence_sentence=tx["sentence"], flags=json.dumps(flags)))
    search.total_count, search.n_fetched = total, len(seen)
    search.status = "ok" if seen else "empty"
    search.error = None
    db.commit()
    return {"gene_symbol": symbol, "status": search.status, "total_count": total,
            "n_fetched": len(seen), "error": None}


# ---------------------------------------------------------------------------
# 摘要：畫面上一列靶點的文獻欄
# ---------------------------------------------------------------------------
def summarize(rows: list) -> dict:
    """把一組 LiteratureEvidence 收成一格摘要。

    `independent_*` 排除循環論證、綜述、撤稿與只靠索引命中的——這才是「可以拿來佐證」的篇數。
    藥材層級與成分層級分開數：只提到槲皮素的論文不是這味藥的證據。
    """
    by_level = {k: 0 for k in LEVELS}
    herb_level = ingredient_only = sentence = circular = 0
    directions = {"down": 0, "up": 0, "mixed": 0}
    independent = []
    for r in rows:
        by_level[r.level] = by_level.get(r.level, 0) + 1
        flags = set(json.loads(r.flags or "[]"))
        kinds = {e.get("kind") for e in json.loads(r.matched_entities or "[]")}
        if "herb" in kinds:
            herb_level += 1
        elif "ingredient" in kinds:
            ingredient_only += 1
        if r.comention == "sentence":
            sentence += 1
        if "circular" in flags:
            circular += 1
        if r.direction in directions:
            directions[r.direction] += 1
        if (r.level not in ("review", "unknown") and "circular" not in flags
                and "retracted" not in flags and r.comention != "index_only"):
            independent.append(r)
    best = min(independent, key=lambda r: r.level_rank) if independent else None
    return {
        "n": len(rows), "by_level": by_level,
        "herb_level": herb_level, "ingredient_only": ingredient_only,
        "same_sentence": sentence, "circular": circular, "directions": directions,
        "independent": len(independent),
        "best_level": best.level if best else None,
        "best_level_label": level_label(best.level) if best else None,
    }


def article_out(r) -> dict:
    return {
        "pmid": r.pmid, "url": PUBMED_URL.format(pmid=r.pmid), "title": r.title,
        "journal": r.journal, "year": r.pub_year, "doi": r.doi,
        "pub_types": json.loads(r.pub_types or "[]"),
        "level": r.level, "level_label": level_label(r.level), "level_rank": r.level_rank,
        "comention": r.comention, "direction": r.direction,
        "matched_entities": json.loads(r.matched_entities or "[]"),
        "evidence_sentence": r.evidence_sentence,
        "flags": json.loads(r.flags or "[]"),
    }
