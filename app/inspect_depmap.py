"""DepMap 匯入後的量級檢核，以及目標一 Step 6 的實際產出。

## 為什麼匯入成功不等於匯對了

`claude/通路富集分析_驗收結果_人參.md` 記過同一件事：程式跑得動、
數字都在合理範圍、畫面很合理，但餵進去的東西或問題的定義是錯的。
KEGG 那次是用「通路數與背景基因數對不對得上外部已知量級」抓出來的。

這支做同樣的事，另外回答一個規格 B 特別警告的問題：

    依賴配對裡有多少是泛必需基因貢獻的？

泛必需基因在**每一株**細胞都依賴，所以它們會用株數把配對表灌滿。
若不先扣掉，任何「選擇性」排序都會被它們洗版——而且看起來很像有訊號。

## 第四節才是 Step 6 對目標一的意義

人參 → 22 個活性成分 → 靶點 → **哪些是特定細胞株的選擇性依賴** →
那些是哪一種癌別的細胞株。

這是整條鏈路第一次從「機轉推測」跨到「可以指名去做哪一株細胞的實驗」。
規格 B 說這是附帶產出，其實它是最有用的一個。

使用方式：

    $env:DATABASE_URL="（Neon 連線字串）"
    python -m app.inspect_depmap
    python -m app.inspect_depmap --herb 336 --out reports\\depmap.md

唯讀，不寫入任何資料。
"""
import argparse
import io
import os
import sys

from app import models, pathways
# 超幾何檢定與 BH 校正一律沿用 app/pathways.py 的實作，不在這裡重寫一份。
# 理由同 v1.38.0 把八處靶點比對收斂到 target_index.py：
# 同一個統計寫兩份就會分岔，而且分岔的那天不會有人發現。
from app.pathways import hypergeom_sf, benjamini_hochberg
from app.database import SessionLocal
from app.target_index import standardized_target_symbols

# 非泛必需基因的選擇性分級（依賴株數佔母體的比例）。
#
# ⚠️ 這些區間**必須互斥且涵蓋全部**，加總要等於非泛必需基因數。
# v1.41.1 的版本把 0 併進第一格、又另外印一列「完全無依賴」，
# 於是同一群基因被數了兩次，看起來像六個互斥的列——
# 「極高選擇性 835」裡其實含了 274 個**一株都不依賴**的基因，真正的是 561。
# 這與 rules.md 記過的「尚未處理 vs 未納入」是同一族錯誤：
# 一張表混兩種語意，加總就對不起來。
SELECTIVE_BANDS = [
    ("完全無依賴", 0.0, 1e-12),      # n_dependent == 0，單獨一格
    ("極高選擇性", 1e-12, 0.01),
    ("高選擇性", 0.01, 0.05),
    ("中度", 0.05, 0.20),
    ("廣泛", 0.20, 0.60),
    ("近泛必需", 0.60, 1.01),
]

# 「強依賴」的慣例界線。門檻 -0.5 只是「有依賴」，-1.0 才是明確的強依賴
# （DepMap 的 Chronos 分數以 -1 對齊泛必需基因的中位數）。
STRONG_EFFECT = -1.0

# 方向性警示用的受體類別（**啟發式、非完整清單**）。
#
# CRISPR 依賴分數量的是「移除這個基因，細胞會不會死」。要把它轉成治療假說，
# 前提是那個化合物**抑制**該靶點——但 TCMSP 的成分–靶點關係沒有方向性，
# 只記錄關聯，不分抑制、活化或單純結合。
#
# 核受體與配體門控受體的天然配體**通常是活化劑**。人參皂苷結合 AHR
# 很可能是活化它而不是抑制它，那麼「AHR 是依賴基因」加上「皂苷結合 AHR」
# 推不出「皂苷會殺死那株細胞」——方向反了效果可能相反。
#
# 這份清單只用來**提醒**，不用來下結論。沒被標記不代表方向就沒問題。
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


def _fix_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _check_db_target():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("⚠️  DATABASE_URL 沒有設定，會讀到本機空的 SQLite。")
        print('    請先執行：$env:DATABASE_URL="（Neon 連線字串）"')
        sys.exit(2)
    print(f"資料庫：{url.split('@')[-1].split('/')[0] if '@' in url else '(local)'}")


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description="DepMap 匯入檢核與 Step 6 產出")
    ap.add_argument("--release", default=None, help="指定 release（預設取最近一次匯入）")
    ap.add_argument("--herb", default="336", help="要分析的藥材 herb_id（預設 336 人参）")
    ap.add_argument("--top", type=int, default=15, help="選擇性靶點列幾筆")
    ap.add_argument("--max-ratio", type=float, default=0.20,
                    help="選擇性門檻：依賴株數佔母體的比例上限（預設 0.20）")
    ap.add_argument("--out", default=None, help="另存 markdown")
    args = ap.parse_args()

    _fix_console()
    _check_db_target()

    buf = io.StringIO()

    def out(line=""):
        print(line)
        buf.write(line + "\n")

    db = SessionLocal()
    try:
        S, D, M = (models.DepMapGeneSummary, models.DepMapGeneDependency,
                   models.DepMapModel)

        run = (db.query(models.DepMapImportRun)
               .order_by(models.DepMapImportRun.created_at.desc()).first())
        if run is None:
            print("找不到任何匯入紀錄，請先跑 python -m app.import_depmap")
            sys.exit(1)
        release = args.release or run.release

        summaries = db.query(S).filter(S.release == release).all()
        if not summaries:
            print(f"release {release} 沒有摘要資料。")
            sys.exit(1)

        n_genes = len(summaries)
        n_lines = max((s.n_lines_total for s in summaries), default=0)
        n_pairs = db.query(D).filter(D.release == release).count()
        essentials = {s.gene_symbol for s in summaries if s.is_common_essential}

        out(f"# DepMap 匯入檢核（release {release}）")
        out()
        out(f"門檻 gene effect ≤ {run.effect_threshold}｜範圍 {run.gene_scope}")
        out()

        # ---------- 一、量級檢核 ----------
        out("## 一、量級檢核")
        out()
        out("| 項目 | 本次 | 該資料庫的已知量級 | 判定 |")
        out("|---|---|---|---|")
        ok_lines = "✓" if 900 <= n_lines <= 1400 else "⚠️"
        out(f"| 細胞株（母體最大值） | {n_lines} | 約 1,100–1,200 | {ok_lines} |")
        out(f"| 掃描基因 | {n_genes} | 取決於已標準化靶點數 | — |")
        ess_pct = len(essentials) / n_genes * 100 if n_genes else 0
        ok_ess = "✓" if 3 <= ess_pct <= 20 else "⚠️"
        out(f"| 泛必需基因 | {len(essentials)}（{ess_pct:.1f}%） | 全基因體約 10% | {ok_ess} |")
        cells = n_genes * n_lines
        dens = n_pairs / cells * 100 if cells else 0
        out(f"| 依賴配對 | {n_pairs} | — | — |")
        out(f"| 佔全部格子 | {dens:.2f}% | — | 見第二節 |")
        out()
        out("**這是判斷有沒有默默出錯的方法**：細胞株數若遠低於千株，"
            "多半是矩陣只讀到一部分；泛必需比例若接近 0 或超過三成，"
            "多半是名單檔沒吃進去或基因符號格式不合。")

        # ---------- 二、泛必需洗版檢查 ----------
        ess_pairs = (db.query(D).filter(D.release == release,
                                        D.gene_symbol.in_(essentials)).count()
                     if essentials else 0)
        sel_pairs = n_pairs - ess_pairs
        out()
        out("## 二、泛必需基因吃掉了多少（規格 B 的核心警告）")
        out()
        out("| | 基因數 | 依賴配對 | 佔全部配對 |")
        out("|---|---|---|---|")
        if n_pairs:
            out(f"| **泛必需** | {len(essentials)} | {ess_pairs} | **{ess_pairs / n_pairs * 100:.1f}%** |")
            out(f"| 非泛必需 | {n_genes - len(essentials)} | {sel_pairs} | {sel_pairs / n_pairs * 100:.1f}% |")
        out()
        if n_pairs and ess_pairs / n_pairs > 0.5:
            out(f"⚠️ **超過一半的依賴配對來自那 {len(essentials)} 個泛必需基因。**")
            out("任何不先扣掉它們的排序，排出來的都是「哪些基因是細胞活著就需要的」，")
            out("不是「哪些是這株腫瘤特別依賴的」。命中泛必需基因是細胞毒性，不是抗腫瘤機轉。")
        out()
        ess_n = n_genes - len(essentials)
        if ess_n and n_lines:
            out(f"扣掉之後，非泛必需基因平均每個在 "
                f"{sel_pairs / ess_n:.1f} 株細胞達門檻"
                f"（母體 {n_lines} 株，約 {sel_pairs / ess_n / n_lines * 100:.1f}%）。"
                f"**這才是選擇性訊號的量級。**")

        # ---------- 三、選擇性分級 ----------
        out()
        out("## 三、非泛必需基因的選擇性分佈")
        out()
        out("| 分級 | 依賴株數佔比 | 基因數 |")
        out("|---|---|---|")
        non_ess = [s for s in summaries if not s.is_common_essential]
        banded = 0
        for label, lo, hi in SELECTIVE_BANDS:
            n = sum(1 for s in non_ess
                    if s.n_lines_total and lo <= s.n_dependent / s.n_lines_total < hi)
            banded += n
            rng = "0%" if label == "完全無依賴" else f"{lo * 100:.0f}–{hi * 100:.0f}%"
            out(f"| {label} | {rng} | {n} |")
        out(f"| **合計** | | **{banded}** |")
        out()
        if banded != len(non_ess):
            out(f"⚠️ 合計 {banded} 與非泛必需基因數 {len(non_ess)} 不符——分級區間有漏或重疊。")
        out("各級互斥，合計必須等於非泛必需基因數。")
        out()
        out("「完全無依賴」不是資料有問題——TCMSP 靶點偏向可成藥蛋白，"
            "其中很多在任何細胞株都不是存活必需基因。")

        # ---------- 四、目標一：藥材的選擇性依賴靶點 ----------
        herb = (db.query(models.TcmspHerb)
                .filter(models.TcmspHerb.id == int(args.herb)).first())
        if herb is None:
            out(f"\n（找不到 herb_id={args.herb}）")
        else:
            ob_min, dl_min = pathways.adme_thresholds(db)
            meta = pathways.active_ingredients(db, herb.id, ob_min, dl_min)
            mol_ids = meta["passed"]
            tar_ids = {r.tar_id for r in
                       db.query(models.TcmspIngredientTarget)
                       .filter(models.TcmspIngredientTarget.mol_id.in_(mol_ids)).all()} \
                if mol_ids else set()

            # 靶點 → 基因符號，只用已標準化的第一層
            t2s = standardized_target_symbols(db)
            syms = set()
            for t in tar_ids:
                syms.update(t2s.get(t, set()))

            sum_by_sym = {s.gene_symbol: s for s in summaries}
            hit = [sum_by_sym[s] for s in syms if s in sum_by_sym]
            hit_sel = [s for s in hit if not s.is_common_essential and s.n_dependent > 0]
            hit_ess = [s for s in hit if s.is_common_essential]

            out()
            out(f"## 四、{herb.herb_cn_name or herb.herb_en_name}"
                f"（herb_id={herb.id}）的選擇性依賴靶點")
            out()
            out(f"活性成分 {meta['passed_count']} 個 → 靶點 {len(tar_ids)} 個 → "
                f"已標準化基因符號 {len(syms)} 個 → DepMap 有資料 {len(hit)} 個")
            out()
            out(f"- 其中**泛必需**：{len(hit_ess)} 個 → **排除**，命中它們是細胞毒性")
            out(f"- 其中**有選擇性依賴**：{len(hit_sel)} 個 ← 這些才是可驗證的標的")
            out()

            if hit_sel:
                # 只按比例排序會失效：幾百個基因並列在「1 株」，
                # 前 N 名等於從並列裡隨便切一段，而 1/1208 剛越過 -0.5 的多半是雜訊
                # （1,143 基因 × 1,208 株，本來就有格子會靠隨機波動越線）。
                # 所以另外數「強依賴」株數，並在同分時用效應量排序。
                # 對應 rules.md 的「兩種排序都要看」。
                deps = (db.query(D).filter(D.release == release,
                                           D.gene_symbol.in_([s.gene_symbol for s in hit_sel]))
                        .all())
                strong = {}
                for d in deps:
                    v = _num(d.gene_effect)
                    if v is not None and v <= STRONG_EFFECT:
                        strong[d.gene_symbol] = strong.get(d.gene_symbol, 0) + 1

                def ratio(x):
                    return x.n_dependent / x.n_lines_total if x.n_lines_total else 9

                # 選擇性是**門檻**，效應量才是**排序**。
                #
                # v1.41.2 用「強依賴株數」排序，結果 PSMG1（653／1208＝54.1%）
                # 排第一——在一半細胞株都依賴的基因當然累積最多強依賴株數，
                # 但那是廣度不是選擇性，已經接近泛必需只是沒進 DepMap 名單。
                # 規格 B 要的正是「排序主軸從命中數翻轉為選擇性」，
                # 用另一種命中數排序等於繞回原點。
                gated = [x for x in hit_sel if ratio(x) <= args.max_ratio]
                dropped = [x for x in hit_sel if ratio(x) > args.max_ratio]
                rows = sorted(gated,
                              key=lambda x: (_num(x.min_effect)
                                             if _num(x.min_effect) is not None else 0))

                n_strong_genes = sum(1 for s in gated if strong.get(s.gene_symbol))
                out(f"### 選擇性門檻內、依效應量排序的前 "
                    f"{min(args.top, len(rows))} 個")
                out()
                out(f"- **門檻**：依賴株數佔母體 ≤ {args.max_ratio * 100:.0f}%"
                    f"（超過就不是選擇性，見下方被刷掉的清單）")
                out(f"- **排序**：最強效應由強到弱")
                out(f"- 強依賴定義：gene effect ≤ {STRONG_EFFECT}"
                    f"（門檻 {run.effect_threshold} 只代表「有依賴」）")
                out()
                out(f"{len(hit_sel)} 個選擇性靶點 → 通過門檻 {len(gated)} 個，"
                    f"其中 **{n_strong_genes} 個**至少在一株細胞達到強依賴。")
                out()
                out("| 基因 | 強依賴株數 | 達門檻株數／母體 | 佔比 | 最強效應 | 最依賴的細胞株 | 癌別 | 方向 |")
                out("|---|---|---|---|---|---|---|---|")
                n_recep = 0
                for s in rows[:args.top]:
                    pct = (s.n_dependent / s.n_lines_total * 100) if s.n_lines_total else 0
                    m = (db.query(M).filter(M.id == s.min_effect_depmap_id).first()
                         if s.min_effect_depmap_id else None)
                    ns = strong.get(s.gene_symbol, 0)
                    rec = is_receptor(s.gene_symbol)
                    if rec:
                        n_recep += 1
                    out(f"| {s.gene_symbol} | {ns if ns else '—'} | "
                        f"{s.n_dependent}／{s.n_lines_total} | "
                        f"{pct:.1f}% | {s.min_effect} | "
                        f"{(m.cell_line_name if m else s.min_effect_depmap_id) or '—'} | "
                        f"{(m.oncotree_primary_disease if m else '—') or '—'} | "
                        f"{'⚠️ 受體' if rec else ''} |")
                out()
                out("#### ⚠️ 方向性：依賴 ≠ 可以用這個化合物抑制")
                out()
                out("CRISPR 依賴分數量的是「**移除**這個基因，細胞會不會死」。"
                    "要把它轉成治療假說，前提是那個化合物**抑制**該靶點。")
                out()
                out("但 **TCMSP 的成分–靶點關係沒有方向性**——只記錄關聯，"
                    "不分抑制、活化或單純結合。")
                out()
                if n_recep:
                    out(f"本表前 {min(args.top, len(rows))} 名中有 **{n_recep} 個標為「受體」**："
                        f"核受體與配體門控受體的天然配體**通常是活化劑**。"
                        f"若化合物是活化而非抑制，"
                        f"「這個靶點是依賴基因」推不出「這個化合物會殺死那株細胞」，"
                        f"**方向反了效果可能相反**。")
                    out()
                out("受體標記是啟發式的、非完整清單，**只用來提醒，不用來下結論**；"
                    "沒被標記也不代表方向就沒問題。要真正解決這件事，"
                    "需要成分–靶點邊的作用方向與證據分層（借鏡文件規格 C）。")
                out()
                out("**怎麼用這張表**：每一列就是一個可執行的驗證方案的起點——")
                out("具體基因、具體細胞株、具體癌別。這比「本方命中 200 個靶點」有用得多，")
                out("而且**可以被否證**。")
                out()
                out(f"⚠️ **強依賴株數為「—」的列請當成雜訊看待。**"
                    f"只在一株細胞、效應又剛越過 {run.effect_threshold} 的配對，"
                    f"在這個規模的矩陣裡本來就會隨機出現。")

                if dropped:
                    # 規格 A：要顯示「本次排序刷掉了什麼、為什麼」，不只顯示留下來的
                    dropped.sort(key=lambda x: -ratio(x))
                    out()
                    out(f"#### 被選擇性門檻刷掉的 {len(dropped)} 個")
                    out()
                    out("| 基因 | 達門檻株數／母體 | 佔比 | 為什麼刷掉 |")
                    out("|---|---|---|---|")
                    for x in dropped[:10]:
                        out(f"| {x.gene_symbol} | {x.n_dependent}／{x.n_lines_total} | "
                            f"{ratio(x) * 100:.1f}% | 依賴範圍過廣，接近泛必需 |")
                    if len(dropped) > 10:
                        out(f"| …另 {len(dropped) - 10} 個 | | | |")
                    out()
                    out("這些不是沒有訊號，而是**訊號不具選擇性**——"
                        "在一半細胞株都依賴的基因，抑制它比較像細胞毒性而不是機轉。"
                        "要看它們請調 `--max-ratio`。")
                out()
                out("⚠️ 但這張表**不是**「人參能治這些癌」。它說的是："
                    "人參的活性成分在 TCMSP 裡被註記為作用於這些靶點，"
                    "而這些靶點在那些細胞株是選擇性依賴。"
                    "**兩件事之間還缺實際的結合與活性驗證**——"
                    "TCMSP 的成分–靶點關係有相當比例是對接預測，不是實測結合。")

            # ---------- 五、lineage 富集 ----------
            if hit_sel:
                gated_syms = [x.gene_symbol for x in gated]
                dep_rows = (db.query(D.depmap_id).filter(
                    D.release == release, D.gene_symbol.in_(gated_syms)).all()
                    if gated_syms else [])
                study_lines = {r[0] for r in dep_rows}

                # 背景**只能**是實際做過 CRISPR 篩選的細胞株。
                #
                # Model.csv 收的是 DepMap 全部細胞株（約 2,154 株），
                # 但 CRISPRGeneEffect 只涵蓋其中約 1,208 株。拿全部當背景，
                # 等於把 900 多株「不可能出現在命中集合裡」的細胞算進母體——
                # 而且各 lineage 的**篩選覆蓋率不同**，於是測到的是覆蓋率而不是生物學。
                # 實測差別：基準命中率 571/2154=26.5% vs 571/1208=47.3%，
                # 膀胱／泌尿道從「倍率 2.13、q=1.7e-3 顯著」掉到倍率約 1.19。
                #
                # 判定「篩選過」的方式：在 depmap_gene_dependency 裡出現過。
                # 每一株篩過的細胞都必然依賴那 96 個泛必需基因，
                # 所以這個集合實務上等於篩選母體——下面有自檢確認這個假設。
                screened = {r[0] for r in
                            db.query(D.depmap_id).filter(D.release == release)
                            .distinct().all()}
                all_models = db.query(M.id, M.oncotree_lineage).filter(
                    M.release == release).all()
                lin_of = {mid: (lin or "（未標註）") for mid, lin in all_models
                          if mid in screened}
                N = len(lin_of)
                n = len(study_lines)

                expected_lines = max((x.n_lines_total for x in summaries), default=0)
                coverage_warn = (expected_lines and
                                 abs(N - expected_lines) > expected_lines * 0.05)

                if N and n:
                    pop, study = {}, {}
                    for mid, lin in lin_of.items():
                        pop[lin] = pop.get(lin, 0) + 1
                    for mid in study_lines:
                        lin = lin_of.get(mid)
                        if lin:
                            study[lin] = study.get(lin, 0) + 1

                    raw = []
                    for lin, K in pop.items():
                        k = study.get(lin, 0)
                        if k == 0:
                            continue
                        raw.append({
                            "lineage": lin, "k": k, "K": K,
                            "fold": (k / n) / (K / N) if K else 0,
                            "p": hypergeom_sf(k, N, K, n),
                        })
                    qs = benjamini_hochberg([r["p"] for r in raw])
                    for r, q in zip(raw, qs):
                        r["q"] = q

                    out()
                    out(f"## 五、{herb.herb_cn_name or herb.herb_en_name}"
                        f"的選擇性依賴集中在哪些 lineage")
                    out()
                    out(f"問的是：**帶有這些選擇性依賴的細胞株，"
                        f"在 lineage 上的分佈有沒有偏離全母體？**")
                    out()
                    out(f"母體 **{N} 株**（實際做過 CRISPR 篩選的細胞株，"
                        f"非 Model.csv 的 {len(all_models)} 株全體）；"
                        f"其中 **{n} 株**至少帶一個本藥材的選擇性依賴"
                        f"（基準命中率 {n / N * 100:.1f}%）。")
                    out()
                    if coverage_warn:
                        out(f"⚠️ 篩選母體 {N} 與摘要記錄的 {expected_lines} 差距超過 5%，"
                            f"請確認匯入是否完整。")
                        out()
                    out("**背景只算篩選過的細胞株。** 拿 Model.csv 全體當背景，"
                        "會把不可能出現在命中集合裡的細胞算進母體，"
                        "而各 lineage 的篩選覆蓋率不同——那樣測到的是覆蓋率，不是生物學。")
                    out()
                    out("依 `rules.md` 的富集規範：**看 q 值不看 p 值**。")
                    out()
                    sig = [r for r in raw if r["q"] < 0.05]
                    raw.sort(key=lambda r: r["q"])
                    out("| Lineage | 命中株／該 lineage 總株數 | 倍率 | q 值 | |")
                    out("|---|---|---|---|---|")
                    for r in raw[:10]:
                        mark = "**顯著**" if r["q"] < 0.05 else ""
                        out(f"| {r['lineage']} | {r['k']}／{r['K']} | "
                            f"{r['fold']:.2f} | {r['q']:.2e} | {mark} |")
                    out()
                    if sig:
                        out(f"達 FDR 顯著的 lineage 有 **{len(sig)}** 個。"
                            f"這回答了規格 B 說的附帶產出：**該做哪一類細胞的實驗。**")
                    else:
                        out("**沒有任何 lineage 達 FDR 顯著。** 這代表選擇性依賴"
                            "大致均勻散佈，先前看到的淋巴系集中很可能只是"
                            "DepMap 母體組成造成的錯覺——"
                            "**這正是需要跟母體比的原因**。")
                    out()
                    out("⚠️ 倍率高但 k 很小的 lineage 檢定力低，"
                        "且 q 值排序會系統性地把它們往後推（`rules.md` 既有規範）。"
                        "兩種排序都要看過再下結論。")

            if hit_ess:
                out()
                out("### 被排除的泛必需靶點")
                out()
                out("　　" + "、".join(sorted(s.gene_symbol for s in hit_ess)))
                out()
                out("這些基因在幾乎每一株細胞都必需。任何藥物只要有細胞毒性都會「命中」它們，"
                    "所以它們**不能**拿來當抗腫瘤機轉的證據。")
    finally:
        db.close()

    if args.out:
        # 資料夾不存在時 open() 會在「全部內容都印完之後」才丟 FileNotFoundError，
        # 看起來像整支失敗，其實報表是好的。自己建起來。
        d = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(d, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(buf.getvalue())
        print(f"\n已寫入 {args.out}")


if __name__ == "__main__":
    main()
