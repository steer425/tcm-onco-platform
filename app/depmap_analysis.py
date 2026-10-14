"""Step 6 細胞株驗證：藥材 → 選擇性依賴靶點的**唯一一份**判定。

`app/inspect_depmap.py`（報表腳本）與 `app/routers/depmap.py`（F1-8 腫瘤細胞頁）
都呼叫這裡。v1.41.1～v1.41.3 在排序規則上錯過三次（比例排序被並列洗版、
強依賴株數排序把 PSMG1 54% 排第一），定案的規則只能存在一個地方——
腳本與畫面若各寫一份，總有一天會給出不同的前 15 名，而且不會有人發現。

## 定案的規則（v1.41.3）

1. 只用**活性成分**（`pathways.active_ingredients()`）與**已標準化**的靶點符號
   （`target_index.standardized_target_symbols()`），不用名稱字詞退路
2. **泛必需基因先排除**——命中它們是細胞毒性，不是抗腫瘤機轉
3. **選擇性當門檻**：達依賴門檻的株數佔母體 ≤ `max_ratio`（預設 20%）
4. **效應量當排序**：最強 gene effect 由強到弱
5. 被門檻刷掉的要列出來並說明原因（規格 A）
6. 受體類標靶加方向性警示（啟發式，只提醒不下結論）

## 刻意不在這裡做的事

**lineage 富集。** 人參的三個「顯著」lineage 經對照基因集檢定，命中率全部落在
隨機對照範圍內（`claude/BCL2結果的正確讀法_與對照檢定_2026-10-06.md`）。
報表腳本保留那一節是因為它會**否定自己的結論**；畫面上只放 q 值、不放對照，
就是選擇性呈現。所以 API 不提供。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import models, pathways
from app.target_index import standardized_target_symbols

# 「強依賴」的慣例界線。匯入門檻 -0.5 只代表「有依賴」，
# DepMap 的 Chronos 分數以 -1 對齊泛必需基因的中位數。
STRONG_EFFECT = -1.0

DEFAULT_MAX_RATIO = 0.20

# DepMap 公開資料的授權義務（CC BY 4.0）：顯示資料的地方必須標註來源與釋出版本。
ATTRIBUTION = ("DepMap, Broad Institute. DepMap Public {release}. "
               "CRISPR gene effect (Chronos). Licensed under CC BY 4.0. https://depmap.org")
DEPMAP_LINE_URL = "https://depmap.org/portal/cell_line/{id}"
DEPMAP_GENE_URL = "https://depmap.org/portal/gene/{symbol}"

# 方向性警示用的受體類別（**啟發式、非完整清單**）。
#
# CRISPR 依賴分數量的是「移除這個基因，細胞會不會死」。要轉成治療假說，前提是
# 化合物**抑制**該靶點；TCMSP 的成分–靶點關係沒有方向性。核受體與配體門控受體的
# 天然配體通常是活化劑——方向反了效果可能相反。沒被標記不代表方向就沒問題。
RECEPTOR_PREFIXES = (
    "NR1", "NR2", "NR3", "NR4", "NR5", "NR6",      # 核受體命名系統
    "RXR", "RAR", "PPAR", "THR", "ESR",
    "ADRA", "ADRB", "CHRM", "CHRN", "HTR", "DRD",  # GPCR 與配體門控離子通道
    "OPR", "ADORA", "GABR", "GRIN", "GRM", "CNR",
)
RECEPTOR_EXACT = {
    "AR", "PGR", "VDR", "AHR", "ESR1", "ESR2", "NR3C1", "NR3C2",
    "PPARG", "PPARA", "PPARD", "RXRA", "RXRB", "RXRG",
}


def is_receptor(sym: str) -> bool:
    s = (sym or "").upper()
    return s in RECEPTOR_EXACT or s.startswith(RECEPTOR_PREFIXES)


def num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def ratio(summary) -> float:
    """依賴株數佔母體的比例。母體為 0 時回 9（永遠過不了門檻）。"""
    return summary.n_dependent / summary.n_lines_total if summary.n_lines_total else 9


def latest_run(db: Session):
    return (db.query(models.DepMapImportRun)
            .order_by(models.DepMapImportRun.created_at.desc()).first())


def resolve_release(db: Session, release: str | None = None):
    """回傳 (release, run)。沒指定就用最近一次匯入。沒有任何匯入回 (None, None)。"""
    run = latest_run(db)
    if release:
        match = (db.query(models.DepMapImportRun)
                 .filter(models.DepMapImportRun.release == release)
                 .order_by(models.DepMapImportRun.created_at.desc()).first())
        return release, (match or run)
    return (run.release if run else None), run


def select_herb_targets(db: Session, herb_id: int, release: str,
                        max_ratio: float = DEFAULT_MAX_RATIO) -> dict:
    """藥材 → 選擇性依賴靶點。回傳 ORM 物件，供腳本與 API 各自呈現。

    回傳鍵：
      meta        pathways.active_ingredients() 的結果
      tar_ids     活性成分連到的 TCMSP 靶點
      t2s         {tar_id: {符號}}（只含已標準化）
      symbols     這些靶點解析出的基因符號
      hit         DepMap 有摘要的
      essential   其中泛必需（排除）
      no_dep      非泛必需、但沒有任何一株達門檻
      selective   非泛必需且至少一株達門檻
      gated       通過選擇性門檻，依最強效應排序
      dropped     被選擇性門檻刷掉，依比例由高到低
      strong      {符號: 強依賴株數}
    """
    S, D = models.DepMapGeneSummary, models.DepMapGeneDependency
    ob_min, dl_min = pathways.adme_thresholds(db)
    meta = pathways.active_ingredients(db, herb_id, ob_min, dl_min)
    mol_ids = meta["passed"]
    tar_ids = ({r.tar_id for r in db.query(models.TcmspIngredientTarget)
                .filter(models.TcmspIngredientTarget.mol_id.in_(mol_ids)).all()}
               if mol_ids else set())

    t2s = standardized_target_symbols(db)
    symbols = set()
    for t in tar_ids:
        symbols.update(t2s.get(t, set()))

    summaries = (db.query(S).filter(S.release == release, S.gene_symbol.in_(list(symbols))).all()
                 if symbols else [])
    hit = summaries
    essential = [s for s in hit if s.is_common_essential]
    no_dep = [s for s in hit if not s.is_common_essential and s.n_dependent <= 0]
    selective = [s for s in hit if not s.is_common_essential and s.n_dependent > 0]

    strong: dict = {}
    if selective:
        deps = (db.query(D).filter(D.release == release,
                                   D.gene_symbol.in_([s.gene_symbol for s in selective])).all())
        for d in deps:
            v = num(d.gene_effect)
            if v is not None and v <= STRONG_EFFECT:
                strong[d.gene_symbol] = strong.get(d.gene_symbol, 0) + 1

    # 選擇性是**門檻**，效應量才是**排序**（v1.41.3 定案，見模組說明）
    gated = sorted([s for s in selective if ratio(s) <= max_ratio],
                   key=lambda s: (num(s.min_effect) if num(s.min_effect) is not None else 0,
                                  s.gene_symbol))
    dropped = sorted([s for s in selective if ratio(s) > max_ratio],
                     key=lambda s: (-ratio(s), s.gene_symbol))

    return {"meta": meta, "tar_ids": tar_ids, "t2s": t2s, "symbols": symbols,
            "hit": hit, "essential": essential, "no_dep": no_dep,
            "selective": selective, "gated": gated, "dropped": dropped,
            "strong": strong, "ob_min": ob_min, "dl_min": dl_min}


def symbol_sources(db: Session, sel: dict) -> dict:
    """{基因符號: [{mol_id, molecule_name, tar_id, target_name, ...}]}

    回答 BCL2 那份文件列的第一個缺口：**哪個成分打這個靶點？**
    只回傳本藥材**活性成分**的邊。邊上的 TCMSP 原始欄位（validated／svm／rf）照實帶出，
    但**尚未分層**（規格 C），呈現時不可當成證據等級。
    """
    want = {s.gene_symbol for s in sel["gated"]} | {s.gene_symbol for s in sel["dropped"]}
    if not want:
        return {}
    tar_by_sym: dict = {}
    for tar, syms in sel["t2s"].items():
        if tar not in sel["tar_ids"]:
            continue
        for sym in syms & want:
            tar_by_sym.setdefault(sym, set()).add(tar)
    tars = set().union(*tar_by_sym.values()) if tar_by_sym else set()
    if not tars:
        return {}
    mol_ids = sel["meta"]["passed"]
    edges = (db.query(models.TcmspIngredientTarget)
             .filter(models.TcmspIngredientTarget.tar_id.in_(list(tars)),
                     models.TcmspIngredientTarget.mol_id.in_(mol_ids)).all())
    names = {i.mol_id: i.molecule_name for i in db.query(models.TcmspIngredient)
             .filter(models.TcmspIngredient.mol_id.in_({e.mol_id for e in edges})).all()}
    tnames = {t.tar_id: t.target_name for t in db.query(models.TcmspTarget)
              .filter(models.TcmspTarget.tar_id.in_(list(tars))).all()}
    out: dict = {}
    for sym, ts in tar_by_sym.items():
        rows = [{"mol_id": e.mol_id, "molecule_name": names.get(e.mol_id),
                 "tar_id": e.tar_id, "target_name": tnames.get(e.tar_id),
                 "tcmsp_validated": e.validated,
                 "tcmsp_svm_score": e.svm_score, "tcmsp_rf_score": e.rf_score}
                for e in edges if e.tar_id in ts]
        rows.sort(key=lambda r: (r["molecule_name"] or "", r["mol_id"]))
        # 同一成分經同一靶點只列一次
        seen, uniq = set(), []
        for r in rows:
            k = (r["mol_id"], r["tar_id"])
            if k not in seen:
                seen.add(k)
                uniq.append(r)
        out[sym] = uniq
    return out
