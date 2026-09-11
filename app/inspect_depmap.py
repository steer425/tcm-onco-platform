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
from app.database import SessionLocal
from app.target_index import standardized_target_symbols

# 非泛必需基因的選擇性分級（依賴株數佔母體的比例）
SELECTIVE_BANDS = [
    ("極高選擇性", 0.0, 0.01),
    ("高選擇性", 0.01, 0.05),
    ("中度", 0.05, 0.20),
    ("廣泛", 0.20, 0.60),
    ("近泛必需", 0.60, 1.01),
]


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
        for label, lo, hi in SELECTIVE_BANDS:
            n = sum(1 for s in non_ess
                    if s.n_lines_total and lo <= s.n_dependent / s.n_lines_total < hi)
            out(f"| {label} | {lo * 100:.0f}–{hi * 100:.0f}% | {n} |")
        n_zero = sum(1 for s in non_ess if s.n_dependent == 0)
        out(f"| 完全無依賴 | 0% | {n_zero} |")
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
                hit_sel.sort(key=lambda s: (s.n_dependent / s.n_lines_total
                                            if s.n_lines_total else 9))
                out(f"### 選擇性最高的 {min(args.top, len(hit_sel))} 個")
                out()
                out("| 基因 | 依賴株數／母體 | 佔比 | 最強效應 | 最依賴的細胞株 | 癌別 |")
                out("|---|---|---|---|---|---|")
                for s in hit_sel[:args.top]:
                    pct = (s.n_dependent / s.n_lines_total * 100) if s.n_lines_total else 0
                    m = (db.query(M).filter(M.id == s.min_effect_depmap_id).first()
                         if s.min_effect_depmap_id else None)
                    out(f"| {s.gene_symbol} | {s.n_dependent}／{s.n_lines_total} | "
                        f"{pct:.1f}% | {s.min_effect} | "
                        f"{(m.cell_line_name if m else s.min_effect_depmap_id) or '—'} | "
                        f"{(m.oncotree_primary_disease if m else '—') or '—'} |")
                out()
                out("**怎麼用這張表**：每一列就是一個可執行的驗證方案的起點——")
                out("具體基因、具體細胞株、具體癌別。這比「本方命中 200 個靶點」有用得多，")
                out("而且**可以被否證**。")
                out()
                out("⚠️ 但這張表**不是**「人參能治這些癌」。它說的是："
                    "人參的活性成分在 TCMSP 裡被註記為作用於這些靶點，"
                    "而這些靶點在那些細胞株是選擇性依賴。"
                    "**兩件事之間還缺實際的結合與活性驗證**——"
                    "TCMSP 的成分–靶點關係有相當比例是對接預測，不是實測結合。")

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
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(buf.getvalue())
        print(f"\n已寫入 {args.out}")


if __name__ == "__main__":
    main()
