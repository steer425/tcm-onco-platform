"""KEGG／Reactome 通路資料同步與富集檢定（目標一 Step 4）。

## 資料從哪來——這一步比看起來便宜

v1.38.0 解析 UniProt 時，順手把每個靶點的 `kegg_id`（`hsa:367`）與
`reactome_ids`（`R-HSA-383280`）一起存進 `tcmsp_target_uniprot` 了，
1751 個靶點裡有 1258 個帶 KEGG 交叉引用。通路分析最貴的那一步
「把蛋白對應到通路」等於已經完成，這裡只需要把通路本身的資訊補上。

## 兩個來源的差別（很容易搞混，弄錯就整個對不起來）

| 來源 | UniProt 交叉引用給的是什麼 | 還缺什麼 |
|---|---|---|
| KEGG | **基因** ID（`hsa:367`） | 基因→通路的對應表，要另外抓 |
| Reactome | **通路** ID（`R-HSA-383280`） | 只缺通路名稱與背景基因數 |

所以 KEGG 要多抓一支 `link/pathway/hsa`。三支都是**整包下載**（bulk），
不是每個靶點打一次——1751 次請求跟 3 次請求的差別。

## 背景基因數為什麼一定要來自外部資料庫

富集檢定問的是「這個藥材命中這條通路的比例，有沒有高於隨機抽樣的期望」。
分母（該通路在全人類基因裡有幾個成員）必須來自 KEGG／Reactome 本身。
**拿我們自己手上的靶點當母體是循環論證**——會讓每條通路看起來都顯著。

## ⚠️ 執行環境

`rest.kegg.jp` 與 `reactome.org` 從 Cowork 沙箱與本機 VM 都連不到（跟 UniProt 一樣），
同步必須在 Render 上跑。測試以 fixture 取代網路層。
"""

from __future__ import annotations

import json
import logging
import math
import re
import sys
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

KEGG_PATHWAY_LIST = "https://rest.kegg.jp/list/pathway/hsa"
KEGG_GENE_PATHWAY_LINK = "https://rest.kegg.jp/link/pathway/hsa"
KEGG_BRITE = "https://rest.kegg.jp/get/br:hsa00001"
REACTOME_UNIPROT_MAP = "https://reactome.org/download/current/UniProt2Reactome_All_Levels.txt"

HUMAN_SPECIES = "Homo sapiens"

# KEGG 官方把 05200–05235 歸在「Cancer: overview」與「Cancer: specific types」兩類。
# 這是 KEGG 自己的分類，不是我們猜的。
KEGG_CANCER_ID_RANGE = (5200, 5235)

# 這些不在 KEGG 的癌症分類裡，但是腫瘤研究的核心訊號通路，
# 對這個平台的用途來說必須標記出來。**這是我們的判斷，不是 KEGG 的分類**，
# 所以獨立成一個看得見的清單，而不是藏在一段 if 條件裡。
KEGG_CANCER_RELATED_EXTRA = {
    "hsa04010",  # MAPK signaling pathway
    "hsa04012",  # ErbB signaling pathway
    "hsa04014",  # Ras signaling pathway
    "hsa04015",  # Rap1 signaling pathway
    "hsa04020",  # Calcium signaling pathway
    "hsa04024",  # cAMP signaling pathway
    "hsa04064",  # NF-kappa B signaling pathway
    "hsa04066",  # HIF-1 signaling pathway
    "hsa04068",  # FoxO signaling pathway
    "hsa04110",  # Cell cycle
    "hsa04115",  # p53 signaling pathway
    "hsa04150",  # mTOR signaling pathway
    "hsa04151",  # PI3K-Akt signaling pathway
    "hsa04210",  # Apoptosis
    "hsa04310",  # Wnt signaling pathway
    "hsa04330",  # Notch signaling pathway
    "hsa04340",  # Hedgehog signaling pathway
    "hsa04350",  # TGF-beta signaling pathway
    "hsa04370",  # VEGF signaling pathway
    "hsa04510",  # Focal adhesion
    "hsa04630",  # JAK-STAT signaling pathway
    "hsa04915",  # Estrogen signaling pathway
}

# ---------------------------------------------------------------------------
# 「疾病類大雜燴通路」的排除規則
# ---------------------------------------------------------------------------
# KEGG 的 Human Diseases 底下有一批通路（結核病、動脈粥狀硬化、B 型肝炎、
# 查加斯氏病…）本質上是**大雜燴**：每一條都塞了 AKT1／BCL2／CASP3/8/9／
# IL1B／IL6／MAPK／NFKB／RELA／TP53 這組通用的發炎與凋亡機器。
#
# 後果是：任何含有這組通用基因的集合，都會對這些疾病「顯著富集」。
# 人參的分析結果裡「結核病 q=1.86e-4」就是這樣來的——那不代表人參治結核病，
# 只代表人參的靶點包含通用發炎凋亡核心。這是 ORA 眾所周知的假象。
#
# 但**不能把整個 Human Diseases 排掉**：癌症通路正好也在這一類底下。
# 所以按 KEGG 自己的 B 層子分類白名單保留，其餘的 Human Diseases 才排除。
KEGG_DISEASE_KEEP = (
    "Cancer: overview",
    "Cancer: specific types",
    "Drug resistance: antineoplastic",
)
DISEASE_CATEGORY_PREFIX = "Human Diseases"


def is_noncancer_disease_pathway(category) -> bool:
    """這條通路是不是「非癌症的疾病類大雜燴」。

    判斷完全依 KEGG 自己的 BRITE 分類，不是猜關鍵字。
    分類抓不到（category 為空）時一律回 False——寧可保留也不要靜默刪掉資料。
    """
    cat = (category or "").strip()
    if not cat.startswith(DISEASE_CATEGORY_PREFIX):
        return False
    return not any(keep in cat for keep in KEGG_DISEASE_KEEP)


# Reactome 沒有像 KEGG 那樣現成的癌症分類可以直接用（要另外抓事件階層檔），
# 所以先用名稱關鍵字判斷，並在頁面上明講這是啟發式的。
REACTOME_CANCER_KEYWORDS = (
    "cancer", "oncogen", "tumor", "tumour", "apoptosis", "cell cycle",
    "p53", "signaling by wnt", "signaling by notch", "pi3k", "mapk",
    "senescence", "dna repair", "dna damage",
)


# ---------------------------------------------------------------------------
# 富集檢定的數學（刻意不引入 scipy）
# ---------------------------------------------------------------------------

def _log_comb(n: int, k: int) -> float:
    """log C(n, k)。用 lgamma 而不是 math.comb 再取 log：

    通路富集的 N 動輒上萬，C(20000, 300) 這種數字用整數算得出來但
    直接取 log 會先溢位成 inf。lgamma 全程在對數空間，不會溢位。
    """
    if k < 0 or k > n:
        return float("-inf")
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1))


def hypergeom_sf(k: int, N: int, K: int, n: int) -> float:
    """超幾何分布的上尾機率 P(X >= k)——過度代表（over-representation）的 p 值。

    參數（用富集分析的語言）：
        N  背景基因總數（該資料庫收錄且有通路註解的人類基因數）
        K  這條通路的基因數
        n  這個藥材命中的基因數（同樣只算有通路註解的）
        k  兩者的交集，也就是「這個藥材打中這條通路的幾個基因」

    邊界情況一律回 1.0（不顯著），不要回 0 或拋例外——
    富集分析會對幾千條通路各跑一次，任何一條炸掉就整份結果不見。
    """
    if k <= 0 or N <= 0 or K <= 0 or n <= 0:
        return 1.0
    if K > N or n > N:
        return 1.0
    upper = min(n, K)
    if k > upper:
        return 1.0

    log_denom = _log_comb(N, n)
    if log_denom == float("-inf"):
        return 1.0

    total = 0.0
    for i in range(k, upper + 1):
        lp = _log_comb(K, i) + _log_comb(N - K, n - i) - log_denom
        if lp > -745:            # exp(-745) 以下就是浮點 0，算了也是加 0
            total += math.exp(lp)
    return min(1.0, max(0.0, total))


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """BH 多重檢定校正，回傳與輸入同順序的 q 值。

    為什麼一定要做：一次對兩三千條通路做檢定，就算全部都是雜訊，
    在 p < 0.05 這條線下也會有一百多條「顯著」。不校正就等於在製造假發現，
    而這些結果是要寫進研究報告的。
    """
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [0.0] * m
    prev = 1.0
    # 由大到小走，維持單調不遞減（BH 的 step-up）
    for rank in range(m, 0, -1):
        idx = order[rank - 1]
        val = min(prev, pvalues[idx] * m / rank)
        q[idx] = val
        prev = val
    return q


# ---------------------------------------------------------------------------
# 外部資料解析（純函式，測試以 fixture 直接餵字串）
# ---------------------------------------------------------------------------

def parse_kegg_pathway_list(text: str) -> dict[str, str]:
    """`hsa04915\\tEstrogen signaling pathway - Homo sapiens (human)` → {id: 名稱}。

    尾巴的 ` - Homo sapiens (human)` 在不同年份的 KEGG 版本有時有、有時沒有，
    一律剝掉，否則同一條通路在兩次同步後會出現兩種名稱。
    """
    out: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 2:
            continue
        pid = parts[0].strip().replace("path:", "")
        name = re.sub(r"\s+-\s+Homo sapiens\s+\(human\)\s*$", "", parts[1].strip())
        if pid and name:
            out[pid] = name
    return out


def parse_kegg_gene_pathway(text: str) -> dict[str, set]:
    """`hsa:10327\\tpath:hsa00010` → {kegg 基因 id: {通路 id, ...}}。"""
    out: dict[str, set] = {}
    for line in text.splitlines():
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 2:
            continue
        gene = parts[0].strip()
        pid = parts[1].strip().replace("path:", "")
        if gene and pid:
            out.setdefault(gene, set()).add(pid)
    return out


def parse_kegg_brite(text: str) -> dict[str, str]:
    """從 BRITE 階層檔取出每條通路的分類字串。

    格式是縮排文字：A = 大類、B = 次類、C = 通路。
    只取 A/B/C，D 開頭的基因列直接跳過（那才是這個檔案體積的來源）。
    """
    out: dict[str, str] = {}
    cat_a = cat_b = ""
    for raw in text.splitlines():
        if not raw:
            continue
        tag = raw[0]
        body = raw[1:].strip()
        if tag == "A":
            cat_a = re.sub(r"^\d+\s*", "", body)
            cat_b = ""
        elif tag == "B":
            cat_b = re.sub(r"^\d+\s*", "", body)
        elif tag == "C":
            m = re.match(r"^(\d{5})\s+(.*)$", body)
            if m:
                out[f"hsa{m.group(1)}"] = " / ".join(x for x in (cat_a, cat_b) if x)
    return out


def parse_reactome_lines(lines) -> dict:
    """UniProt2Reactome_All_Levels.txt → {"pathways": {...}, "background_total": int}。

    欄位：UniProt / 通路 ID / URL / 事件名稱 / 證據代碼 / 物種

    記憶體考量（Render free plan 只有 512MB，這不是理論疑慮）：
    這個檔案是數十 MB、上百萬列的 (蛋白, 通路) 配對，所以吃 iterator 而不是整份字串。
    每條通路的成員要去重（同一對會因為證據代碼不同重複出現），必須存成集合；
    但 accession 字串用 `sys.intern` 共用——人類只有一萬多個不重複 accession，
    interning 之後上百萬個參考指向的是同一批字串物件，省下來的是實際的記憶體。

    `background_total` 是全部有 Reactome 註解的人類蛋白數，也就是富集檢定的 N。
    這個值必須是**實際數到的不重複 accession 數**，不能用估的——
    N 估錯會讓每一條通路的 p 值一起偏移，而且偏得看不出來。
    """
    acc: dict[str, dict] = {}
    all_accessions: set = set()
    for raw in lines:
        parts = raw.rstrip("\n").split("\t")
        if len(parts) < 6:
            continue
        uniprot, pid, _url, name, _evidence, species = parts[:6]
        if species.strip() != HUMAN_SPECIES or not pid.startswith("R-HSA-"):
            continue
        uniprot = sys.intern(uniprot.strip())
        all_accessions.add(uniprot)
        entry = acc.setdefault(pid, {"name": name.strip(), "accessions": set()})
        entry["accessions"].add(uniprot)

    return {
        "pathways": {pid: {"name": v["name"], "gene_count": len(v["accessions"])}
                     for pid, v in acc.items()},
        "background_total": len(all_accessions),
    }


def is_cancer_pathway(source: str, pathway_id: str, name: str) -> bool:
    if source == "kegg":
        m = re.match(r"^hsa(\d{5})$", pathway_id or "")
        if m:
            num = int(m.group(1))
            if KEGG_CANCER_ID_RANGE[0] <= num <= KEGG_CANCER_ID_RANGE[1]:
                return True
        return pathway_id in KEGG_CANCER_RELATED_EXTRA
    low = (name or "").lower()
    return any(kw in low for kw in REACTOME_CANCER_KEYWORDS)


# ---------------------------------------------------------------------------
# 外部抓取（唯一會碰網路的地方，測試裡整支被取代）
# ---------------------------------------------------------------------------

def fetch_text(url: str, timeout: float = 120.0) -> str:
    headers = {"User-Agent": "TCM-Onco-Platform/1.0 (research; pathway enrichment)"}
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def fetch_lines(url: str, timeout: float = 300.0):
    """串流讀取大檔，逐行吐出。整份 read() 進記憶體會撐爆 Render free plan。"""
    headers = {"User-Agent": "TCM-Onco-Platform/1.0 (research; pathway enrichment)"}
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                yield line


def fetch_kegg() -> dict:
    """回傳 {pathways: {id: {name, category}}, gene_to_pathways: {kegg_gene: {pid}}}。"""
    names = parse_kegg_pathway_list(fetch_text(KEGG_PATHWAY_LIST))
    links = parse_kegg_gene_pathway(fetch_text(KEGG_GENE_PATHWAY_LINK))
    try:
        categories = parse_kegg_brite(fetch_text(KEGG_BRITE))
    except Exception as exc:  # noqa: BLE001
        # 分類抓不到不該讓整個同步失敗——通路名稱與基因對應才是必要的，
        # 分類只是畫面上的分組標籤
        logger.warning("KEGG BRITE 分類抓取失敗，改為無分類：%s", exc)
        categories = {}

    counts: dict[str, int] = {}
    for pids in links.values():
        for pid in pids:
            counts[pid] = counts.get(pid, 0) + 1

    return {
        "pathways": {pid: {"name": name,
                           "category": categories.get(pid),
                           "gene_count": counts.get(pid, 0)}
                     for pid, name in names.items()},
        "gene_to_pathways": links,
        "background_total": len(links),
    }


def fetch_reactome() -> dict:
    return parse_reactome_lines(fetch_lines(REACTOME_UNIPROT_MAP))


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 資料庫層：同步與富集查詢
# ---------------------------------------------------------------------------

from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402

BACKGROUND_KEY = "pathway_background_{source}"


def get_background_total(db: Session, source: str) -> int:
    row = (db.query(models.SystemSetting)
           .filter(models.SystemSetting.key == BACKGROUND_KEY.format(source=source)).first())
    try:
        return int(row.value) if row and row.value else 0
    except (TypeError, ValueError):
        return 0


def _set_background_total(db: Session, source: str, total: int) -> None:
    key = BACKGROUND_KEY.format(source=source)
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if row:
        row.value = str(total)
    else:
        db.add(models.SystemSetting(key=key, value=str(total)))


def sync_pathways(db: Session, source: str, data: dict) -> dict:
    """把抓回來的通路目錄寫進 `pathways`，並重建 `target_pathways`。

    通路名稱與背景基因數**會覆蓋**（那是外部資料庫的事實，我們沒有話語權）；
    三語系翻譯欄位**絕不覆蓋**——那是人補上去的，跟 feature_config 那條
    「不要覆蓋管理者調整過的欄位」是同一個道理（v1.32.4 的教訓）。
    """
    catalog = data.get("pathways") or {}
    background_total = int(data.get("background_total") or 0)

    existing = {p.pathway_id: p for p in db.query(models.Pathway)
                .filter(models.Pathway.source == source).all()}
    created = updated = 0
    for pid, info in catalog.items():
        name = (info.get("name") or "").strip()
        if not name:
            continue
        row = existing.get(pid)
        if row is None:
            row = models.Pathway(source=source, pathway_id=pid, name=name)
            db.add(row)
            existing[pid] = row
            created += 1
        else:
            row.name = name
            updated += 1
        row.category = info.get("category") or row.category
        row.background_gene_count = info.get("gene_count")
        row.is_cancer_related = is_cancer_pathway(source, pid, name)
        row.synced_at = datetime.utcnow()

    _set_background_total(db, source, background_total)
    db.flush()

    linked = link_targets(db, source, data)
    db.commit()
    return {"source": source, "pathways_created": created,
            "pathways_updated": updated, "background_total": background_total, **linked}


def link_targets(db: Session, source: str, data: dict) -> dict:
    """依既有的 UniProt 映射，重建這個來源的靶點↔通路關聯。

    整批砍掉重建而不是增量更新：這張表是推導資料，來源一變就該整份重算。
    增量更新要處理「上次連上、這次沒有」的情況，那才是真正容易出錯的地方。
    """
    pathway_by_pid = {p.pathway_id: p for p in db.query(models.Pathway)
                      .filter(models.Pathway.source == source).all()}

    (db.query(models.TargetPathway)
     .filter(models.TargetPathway.source == source)
     .delete(synchronize_session=False))
    db.flush()

    rows = (db.query(models.TcmspTargetUniprot)
            .filter(models.TcmspTargetUniprot.status.in_(("auto", "confirmed"))).all())

    gene_to_pathways = data.get("gene_to_pathways") or {}
    seen: set = set()
    links = 0
    targets_with_pathway: set = set()

    for r in rows:
        if source == "kegg":
            if not r.kegg_id:
                continue
            pids = gene_to_pathways.get(r.kegg_id, set())
        else:
            try:
                pids = set(json.loads(r.reactome_ids or "[]"))
            except (TypeError, ValueError):
                continue

        for pid in pids:
            p = pathway_by_pid.get(pid)
            if p is None:
                continue
            key = (r.tar_id, p.id)
            if key in seen:
                continue
            seen.add(key)
            db.add(models.TargetPathway(
                tar_id=r.tar_id, pathway_ref_id=p.id, source=source,
                via_symbol=r.gene_symbol, via_accession=r.accession))
            links += 1
            targets_with_pathway.add(r.tar_id)

    db.flush()
    return {"links": links, "targets_with_pathway": len(targets_with_pathway)}


# ADME 篩選門檻。這不是我們發明的數字，是 TCMSP 原始論文的建議值，
# 也是 docs/2026_goals.md 裡「目標一 Step 1」白紙黑字寫的條件。
# 存成系統設定讓管理者可調，但預設值不要亂動——動了就跟文獻上的方法學對不起來。
DEFAULT_OB_MIN = 30.0     # 口服生體可用率 (%)
DEFAULT_DL_MIN = 0.18     # 類藥性
OB_KEY, DL_KEY = "tcmsp_ob_threshold", "tcmsp_dl_threshold"


def _setting_float(db: Session, key: str, default: float) -> float:
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    try:
        return float(row.value) if row and row.value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def adme_thresholds(db: Session) -> tuple:
    return (_setting_float(db, OB_KEY, DEFAULT_OB_MIN),
            _setting_float(db, DL_KEY, DEFAULT_DL_MIN))


def _num(value):
    """TCMSP 的 ob／dl 存成字串（可攜型別規範），而且會有空字串與 'NA'。

    解析不出來時回 None 而不是 0——當成 0 會讓那個成分被靜默篩掉，
    看起來像「這個成分不活性」，實際上是「這筆資料缺值」。兩件事必須分得開。
    """
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def active_ingredients(db: Session, herb_id, ob_min: float, dl_min: float) -> dict:
    """套用 OB／DL 篩選，回傳篩選前後的成分清單與統計。

    **為什麼一定要篩**：TCMSP 收錄的是這個藥材裡「偵測得到」的所有化合物，
    絕大多數口服吸收率極低或根本不具類藥性，到不了體內任何靶點。
    不篩就等於宣稱人參的每一個化合物都在體內作用——那不是保守，是錯的。

    實測差別（人參，2026-08-27）：不篩 196 個靶點，篩了之後降到接近
    docs/2026_goals.md 記載的「22 個活性成分、約 109 個不重複靶點基因」。

    缺值（`ob`／`dl` 是空字串或 'NA'）一律**排除**並單獨計數。
    把缺值當成通過會讓篩選形同虛設；當成 0 則無法跟「真的很低」區分，
    所以獨立回報，讓使用者知道有多少筆是因為資料不全而被排除的。
    """
    rows = (db.query(models.TcmspIngredient)
            .join(models.TcmspHerbIngredient,
                  models.TcmspHerbIngredient.mol_id == models.TcmspIngredient.mol_id)
            .filter(models.TcmspHerbIngredient.herb_id == herb_id).all())

    passed, missing = [], 0
    for ing in rows:
        ob, dl = _num(ing.ob), _num(ing.dl)
        if ob is None or dl is None:
            missing += 1
            continue
        if ob >= ob_min and dl >= dl_min:
            passed.append(ing.mol_id)

    return {"total": len(rows), "passed": passed,
            "passed_count": len(passed), "missing_adme": missing,
            "ob_min": ob_min, "dl_min": dl_min}


def targets_for_herb(db: Session, herb_id, apply_adme: bool = True,
                     ob_min: float = None, dl_min: float = None) -> tuple:
    """藥材 → 成分 → 靶點。回傳 (tar_id 集合, 成分篩選統計)。

    `apply_adme=True`（預設）會先套用 OB／DL 篩選，也就是
    docs/2026_goals.md 目標一 Step 1 定義的活性成分條件。
    關掉只該用在「想看未篩選有多少」的對照，不該當成正式分析結果。
    """
    if apply_adme:
        if ob_min is None or dl_min is None:
            ob_min, dl_min = adme_thresholds(db)
        meta = active_ingredients(db, herb_id, ob_min, dl_min)
        mol_ids = meta["passed"]
    else:
        mol_ids = [r.mol_id for r in db.query(models.TcmspHerbIngredient)
                   .filter(models.TcmspHerbIngredient.herb_id == herb_id).all()]
        meta = {"total": len(mol_ids), "passed_count": len(mol_ids),
                "missing_adme": 0, "ob_min": None, "dl_min": None}

    meta.pop("passed", None)
    if not mol_ids:
        return set(), meta
    tar_ids = {r.tar_id for r in db.query(models.TcmspIngredientTarget)
               .filter(models.TcmspIngredientTarget.mol_id.in_(mol_ids)).all()}
    return tar_ids, meta


# 冗餘判定門檻。一條通路的命中基因如果有這個比例以上已經出現在更高名次的通路裡，
# 就標記為冗餘——它沒有帶來新的觀察，只是同一組基因的另一種通路定義。
#
# 0.8 這個值的理由：人參的 p53 signaling 命中 BAX／BCL2／CASP3／CASP8／CASP9／CDK1，
# 其中五個跟排在前面的 Apoptosis 完全相同（5/6 = 0.83）。那兩條並列在報告裡
# 會被讀成兩項獨立證據，實際上是同一個觀察被 KEGG 的通路定義重複計入。
# 門檻訂太低會把真正互補的通路也標成冗餘，訂太高則抓不到這種明顯重複。
REDUNDANCY_THRESHOLD = 0.8


def annotate_redundancy(ranked: list) -> list:
    """依統計證據順序（p 值由小到大）標記冗餘，並算出每條的「新增基因」。

    為什麼需要：KEGG／Reactome 的通路定義大量重疊，
    同一組基因會同時落在凋亡、p53、癌症總覽等好幾條通路裡。
    畫面上並列成好幾項會看起來像交叉印證，**實際上是一個觀察被算了很多次**。

    每一條會多兩個資訊：
      `new_symbols`   這條通路命中、但更高名次都沒出現過的基因
      `redundant_with` 重疊比例最高且達門檻的那條更高名次通路（沒有則為 None）
    """
    seen: set = set()
    prior: list = []          # [(pathway_id, name, rank, 命中集合)]
    for idx, item in enumerate(ranked):
        hits = set(item["symbols"])
        item["new_symbols"] = sorted(hits - seen)

        best = None
        for pid, name, rank, prev_hits in prior:
            if not hits:
                break
            ratio = len(hits & prev_hits) / len(hits)
            if ratio >= REDUNDANCY_THRESHOLD and (best is None or ratio > best["ratio"]):
                best = {"pathway_id": pid, "name": name, "rank": rank,
                        "shared": len(hits & prev_hits), "total": len(hits),
                        "ratio": round(ratio, 3)}
        item["redundant_with"] = best

        prior.append((item["pathway"].pathway_id, item["pathway"].name, idx + 1, hits))
        seen |= hits
    return ranked


def enrich(db: Session, tar_ids, source: str = "kegg",
           background: str = "genome", cancer_only: bool = False,
           exclude_noncancer_disease: bool = False,
           sort: str = "p", limit: int = 50) -> dict:
    """對一組靶點做通路過度代表分析（ORA）。

    ## 樣本數與母體，絕對不能被「只顯示哪些通路」影響（v1.39.3 修正的錯誤）

    這是最容易寫錯、而且錯了不會有徵兆的地方。

    `cancer_only` 與 `exclude_noncancer_disease` 是**要測哪些通路**的篩選，
    不是**樣本怎麼算**的篩選。v1.39.2 之前把它們套在建立索引之前，
    結果勾「只看癌症相關通路」時 n 從 92 掉到 60——因為 n 變成了
    「只在癌症通路裡有註解的基因數」。

    那等於先把樣本限縮到癌症通路的基因，再問「這些基因是不是集中在癌症通路」，
    是循環論證。實測倍率被灌到 20 倍、q 值到 1e-15，看起來像重大發現，
    其實是自己造出來的。

    正確做法：
      - `n`（樣本）與 `N`（母體）一律用**該來源全部的通路註解**計算，與顯示篩選無關
      - 篩選只決定「哪些通路進入檢定與 BH 校正」
      - 一條通路的 p 值，不會因為旁邊多顯示或少顯示幾條而改變

    ## 在基因符號空間計算，不是 tar_id 空間

    TCMSP 有多個靶點指向同一個基因（同工異構物、次單元），
    照 tar_id 數會把同一個基因重複計入，命中數被灌水、p 值跟著失真。

    ## 兩種背景集，畫面上要讓使用者看得到自己選了哪一種

    `genome`（預設，學界慣例）
        母體是 KEGG／Reactome 收錄的全部人類基因。回答的是
        「這條通路在這個藥材的靶點裡，是否比在全人類基因裡更常出現」。
        缺點：TCMSP 的靶點本來就偏向可成藥的蛋白，所以訊號傳導、
        代謝這類通路會系統性地被高估。

    `tcmsp`
        母體改成「全部已標準化的 TCMSP 靶點基因」。回答的是
        「這條通路在**這個**藥材裡，是否比在中藥靶點整體裡更常出現」。
        這會把上面那個偏差消掉，更適合拿來比較不同藥材。
        缺點：不是慣例，寫進論文要額外說明。
    """
    tar_ids = set(tar_ids or ())

    # 一律撈全部，不在這裡篩——篩選只影響「測哪些」，不影響 n 與 N
    all_links = (db.query(models.TargetPathway, models.Pathway)
                 .join(models.Pathway,
                       models.Pathway.id == models.TargetPathway.pathway_ref_id)
                 .filter(models.TargetPathway.source == source).all())

    study_hits: dict = {}
    study_symbols: set = set()
    tcmsp_pathway_symbols: dict = {}
    tcmsp_symbols: set = set()
    pathway_meta: dict = {}

    for link, pathway in all_links:
        sym = (link.via_symbol or "").upper()
        if not sym:
            continue
        pathway_meta[pathway.id] = pathway
        tcmsp_pathway_symbols.setdefault(pathway.id, set()).add(sym)
        tcmsp_symbols.add(sym)
        if link.tar_id in tar_ids:
            study_hits.setdefault(pathway.id, set()).add(sym)
            study_symbols.add(sym)

    n = len(study_symbols)

    # 決定哪些通路要進入檢定（只影響 BH 的 m，不影響 n／N）
    testable = set(pathway_meta.keys())
    excluded_disease = 0
    if cancer_only:
        testable = {pid for pid in testable if pathway_meta[pid].is_cancer_related}
    if exclude_noncancer_disease:
        before = len(testable)
        testable = {pid for pid in testable
                    if not is_noncancer_disease_pathway(pathway_meta[pid].category)}
        excluded_disease = before - len(testable)

    if background == "tcmsp":
        N = len(tcmsp_symbols)
        pathway_K = {pid: len(syms) for pid, syms in tcmsp_pathway_symbols.items()}
    else:
        N = get_background_total(db, source)
        pathway_K = {pid: (pathway_meta[pid].background_gene_count or 0)
                     for pid in pathway_meta}

    if n == 0:
        return {"source": source, "background": background, "study_gene_count": 0,
                "background_total": N, "total_tested": 0, "significant_count": 0,
                "excluded_disease_pathways": excluded_disease, "items": [],
                "note": "這個藥材的靶點沒有任何一個對應到通路註解"
                        "（可能尚未標準化，或活性成分篩選後沒有剩下有註解的靶點）"}

    raw = []
    for pid, syms in study_hits.items():
        if pid not in testable:
            continue
        K = pathway_K.get(pid, 0)
        k = len(syms)
        if K <= 0:
            continue
        raw.append({"pathway": pathway_meta[pid], "k": k, "K": K,
                    "symbols": sorted(syms),
                    "p_value": hypergeom_sf(k, N, K, n)})

    qs = benjamini_hochberg([r["p_value"] for r in raw])
    for r, qv in zip(raw, qs):
        r["q_value"] = qv
        r["fold"] = round((r["k"] / n) / (r["K"] / N), 3) if N and r["K"] else None

    # 冗餘一律依「統計證據順序」判定，跟使用者選哪種排序無關——
    # 誰是誰的重複，是資料的事實，不該因為畫面怎麼排而改變
    raw.sort(key=lambda r: (r["p_value"], -r["k"]))
    annotate_redundancy(raw)
    p_rank = {id(r): i + 1 for i, r in enumerate(raw)}

    if sort == "fold":
        # 依倍率排序的用途：p 值天生偏袒基因數多的大通路
        #（k 大檢定力高），依 p 值排會把高特異性的小通路往後推。
        # 人參的 Apoptosis 是 19.2 倍卻排第 20，就是這樣來的。
        raw.sort(key=lambda r: (-(r["fold"] or 0), r["p_value"]))

    items = [{
        "rank": i + 1,
        "p_rank": p_rank[id(r)],
        "pathway_id": r["pathway"].pathway_id,
        "name": r["pathway"].name,
        "name_tw": r["pathway"].name_tw,
        "category": r["pathway"].category,
        "is_cancer_related": bool(r["pathway"].is_cancer_related),
        "hit_count": r["k"],
        "pathway_gene_count": r["K"],
        "hit_symbols": r["symbols"],
        "new_symbols": r["new_symbols"],
        "redundant_with": r["redundant_with"],
        "p_value": r["p_value"],
        "q_value": r["q_value"],
        "fold_enrichment": r["fold"],
    } for i, r in enumerate(raw[:limit])]

    significant = [r for r in raw if r["q_value"] < 0.05]
    return {"source": source, "background": background, "sort": sort,
            "study_gene_count": n, "background_total": N,
            "total_tested": len(raw),
            "significant_count": len(significant),
            # 去除冗餘後還剩幾條——這才是「有幾項獨立發現」的答案。
            # 顯著通路數本身會被通路定義的重疊灌水。
            "independent_count": sum(1 for r in significant if not r["redundant_with"]),
            "excluded_disease_pathways": excluded_disease,
            "items": items}
