"""匯入 DepMap 細胞株與基因依賴資料（目標一 Step 6）。

## 為什麼是「你自己下載檔案，再跑這支腳本」

外部生醫資料庫從 Cowork 沙箱與本機 VM 都連不到（見
`claude/上版流程與跨對話慣例.md` 第 5 節），DepMap 也不例外。
所以流程跟 `import_tcmsp_data.py` 一樣：檔案由人下載，腳本負責解析與寫入。

## 需要哪些檔案

從 https://depmap.org/portal/data_page/ 下載該季 Public 釋出版：

    Model.csv                        細胞株主檔（必要）
    CRISPRGeneEffect.csv             Chronos 基因效應矩陣（必要，很大）
    CRISPRInferredCommonEssentials.csv   泛必需基因名單（必要）

授權：DepMap 自產資料為 **CC BY 4.0**，允許商業使用與再散布，
但**必須標註出處**。前端顯示這些資料的頁面要寫明資料來源與釋出版本。
（DepMap 入口網站上由其他計畫提供的資料可能有不同授權，逐檔確認。）

## 為什麼只存達門檻的配對

完整矩陣約 1,150 株 × 18,400 基因 = 兩千多萬個值；即使只留 TCMSP 靶點基因
也有上百萬列，Neon 免費層放不下。所以只寫入 `gene_effect <= threshold` 的配對，
另外替每個基因存一份跨全母體的摘要（見 `models.DepMapGeneSummary` 的說明）。

**篩選發生在匯入時**，所以執行期不需要對數值做範圍查詢，
數值可以照全站慣例存成 String。

使用方式：

    $env:DATABASE_URL="（Neon 連線字串）"
    python -m app.import_depmap D:\depmap_24Q2 --release 24Q2

    # 只掃 TCMSP 靶點基因（預設）；要全基因請明確指定，注意資料量
    python -m app.import_depmap D:\depmap_24Q2 --release 24Q2 --genes all

    # 調整依賴門檻（預設 -0.5）
    python -m app.import_depmap D:\depmap_24Q2 --release 24Q2 --threshold -0.3

匯入會**取代**同一 release 的既有資料，可重複執行。
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

from app import models
from app.database import SessionLocal, engine, Base
from app.target_index import standardized_symbols

# DepMap 的基因欄位名長這樣：`A1BG (1)` —— 符號 + Entrez ID
GENE_COL_RE = re.compile(r"^\s*([A-Za-z0-9\-_.@/]+)\s*\((\d+)\)\s*$")

DEFAULT_THRESHOLD = -0.5
CHUNK = 5000

MODEL_FILE = "Model.csv"
EFFECT_FILE = "CRISPRGeneEffect.csv"
ESSENTIAL_FILE = "CRISPRInferredCommonEssentials.csv"


def _fix_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _check_db_target():
    """DATABASE_URL 沒設會靜默退回本機 SQLite——這支會寫入幾萬列，
    寫到本機空檔案上完全看不出異狀，是最容易誤判「已經匯入了」的坑。"""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("=" * 72)
        print("⚠️  DATABASE_URL 沒有設定，會寫入本機 SQLite（tcm_platform.db）。")
        print("    匯入會顯示成功，但正式資料庫完全沒變。")
        print()
        print('    請先執行：$env:DATABASE_URL="（Neon 連線字串）"')
        print("=" * 72)
        sys.exit(2)
    print(f"資料庫：{url.split('@')[-1].split('/')[0] if '@' in url else '(local sqlite)'}")


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _gene_symbol(col: str):
    m = GENE_COL_RE.match(col or "")
    return m.group(1).upper() if m else None


def _num(v):
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _require(folder: Path, name: str) -> Path:
    p = folder / name
    if not p.is_file():
        print(f"找不到 {name}（預期位置：{p}）")
        print("請從 https://depmap.org/portal/data_page/ 下載該季 Public 釋出版。")
        sys.exit(1)
    return p


def load_models(db, path: Path, release: str) -> int:
    """細胞株主檔。DepMap 的欄位名歷年有變，所以每個欄位都給幾個候選名稱。"""
    def pick(row, *names):
        for n in names:
            if row.get(n) not in (None, ""):
                return row[n]
        return None

    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    db.query(models.DepMapModel).delete()
    db.bulk_insert_mappings(models.DepMapModel, [
        {
            "id": pick(r, "ModelID", "DepMap_ID"),
            "cell_line_name": pick(r, "CellLineName", "cell_line_name"),
            "stripped_cell_line_name": pick(r, "StrippedCellLineName"),
            "oncotree_lineage": pick(r, "OncotreeLineage", "lineage"),
            "oncotree_primary_disease": pick(r, "OncotreePrimaryDisease", "primary_disease"),
            "oncotree_subtype": pick(r, "OncotreeSubtype", "Subtype"),
            "release": release,
        }
        for r in rows if pick(r, "ModelID", "DepMap_ID")
    ])
    db.commit()
    return len(rows)


def load_common_essentials(path: Path) -> set:
    """泛必需基因名單。欄位通常叫 Essentials，內容格式與矩陣欄位名相同。"""
    out = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            sym = _gene_symbol(row[0]) or row[0].strip().upper()
            if sym and sym != "ESSENTIALS":
                out.add(sym)
    return out


def import_effects(db, path: Path, release: str, threshold: float,
                   wanted: set | None):
    """逐列（逐細胞株）串流讀取矩陣。

    **不要整個讀進記憶體**：完整檔案幾百 MB，pandas 讀進來會吃掉數 GB。
    這裡一次只留一列，累加每個基因的統計量，只把達門檻的配對收集起來。
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)

        keep = []          # (欄位索引, 基因符號)
        for i, col in enumerate(header[1:], start=1):
            sym = _gene_symbol(col)
            if sym and (wanted is None or sym in wanted):
                keep.append((i, sym))

        if not keep:
            print("矩陣裡沒有任何符合的基因欄位。")
            print("若是用預設的 TCMSP 靶點範圍，代表靶點標準化還沒跑過，")
            print("或這一版矩陣的欄位格式不是 `SYMBOL (ENTREZ)`。")
            sys.exit(1)

        print(f"矩陣欄位 {len(header) - 1} 個，本次掃描 {len(keep)} 個基因")

        # 每個基因的累加器：n, sum, sumsq, min, argmin
        stats = {sym: [0, 0.0, 0.0, None, None] for _, sym in keep}
        pending = []
        n_models = n_rows = 0

        for row in reader:
            if not row:
                continue
            model_id = (row[0] or "").strip()
            if not model_id:
                continue
            n_models += 1

            for idx, sym in keep:
                if idx >= len(row):
                    continue
                v = _num(row[idx])
                if v is None:
                    continue
                st = stats[sym]
                st[0] += 1
                st[1] += v
                st[2] += v * v
                if st[3] is None or v < st[3]:
                    st[3], st[4] = v, model_id

                if v <= threshold:
                    pending.append({
                        "depmap_id": model_id, "gene_symbol": sym,
                        "gene_effect": f"{v:.6g}", "release": release,
                    })

            if len(pending) >= CHUNK:
                db.bulk_insert_mappings(models.DepMapGeneDependency, pending)
                db.commit()
                n_rows += len(pending)
                pending = []
                print(f"  已寫入 {n_rows} 列依賴配對（掃過 {n_models} 株）...")

        if pending:
            db.bulk_insert_mappings(models.DepMapGeneDependency, pending)
            db.commit()
            n_rows += len(pending)

    return stats, n_models, n_rows, len(keep)


def write_summaries(db, stats: dict, essentials: set, release: str, threshold: float):
    rows = []
    for sym, (n, s, sq, mn, argmin) in stats.items():
        if n == 0:
            continue
        mean = s / n
        var = max(sq / n - mean * mean, 0.0)
        n_dep = (db.query(models.DepMapGeneDependency)
                 .filter(models.DepMapGeneDependency.gene_symbol == sym,
                         models.DepMapGeneDependency.release == release).count())
        rows.append({
            "gene_symbol": sym, "release": release,
            "n_lines_total": n, "n_dependent": n_dep,
            "mean_effect": f"{mean:.6g}", "sd_effect": f"{math.sqrt(var):.6g}",
            "min_effect": f"{mn:.6g}" if mn is not None else None,
            "min_effect_depmap_id": argmin,
            "is_common_essential": sym in essentials,
        })
    db.bulk_insert_mappings(models.DepMapGeneSummary, rows)
    db.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="匯入 DepMap 細胞株與基因依賴資料")
    ap.add_argument("folder", help="放著 Model.csv / CRISPRGeneEffect.csv / "
                                   "CRISPRInferredCommonEssentials.csv 的資料夾")
    ap.add_argument("--release", required=True, help="釋出版本，例如 24Q2（會記進匯入紀錄）")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help=f"依賴門檻，gene effect 小於等於此值才寫入（預設 {DEFAULT_THRESHOLD}）")
    ap.add_argument("--genes", choices=["tcmsp", "all"], default="tcmsp",
                    help="掃描範圍：tcmsp=只掃已標準化的 TCMSP 靶點基因（預設）；"
                         "all=全部基因（資料量會大很多）")
    args = ap.parse_args()

    _fix_console()
    _check_db_target()

    folder = Path(args.folder)
    model_path = _require(folder, MODEL_FILE)
    effect_path = _require(folder, EFFECT_FILE)
    essential_path = _require(folder, ESSENTIAL_FILE)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        wanted = None
        if args.genes == "tcmsp":
            wanted = standardized_symbols(db)
            print(f"TCMSP 已標準化的基因符號：{len(wanted)} 個")
            if not wanted:
                print("一個都沒有——請先到後台 F1-4 跑完靶點標準化，或用 --genes all。")
                sys.exit(1)

        print(f"依賴門檻：gene effect <= {args.threshold}")
        print("清除同一 release 的既有資料...")
        db.query(models.DepMapGeneDependency).filter(
            models.DepMapGeneDependency.release == args.release).delete()
        db.query(models.DepMapGeneSummary).filter(
            models.DepMapGeneSummary.release == args.release).delete()
        db.commit()

        print("匯入細胞株主檔...")
        n_models_file = load_models(db, model_path, args.release)
        print(f"  {n_models_file} 株")

        essentials = load_common_essentials(essential_path)
        print(f"泛必需基因名單：{len(essentials)} 個")

        print("串流讀取基因效應矩陣...")
        stats, n_models, n_rows, n_genes = import_effects(
            db, effect_path, args.release, args.threshold, wanted)

        print("寫入每基因摘要...")
        n_sum = write_summaries(db, stats, essentials, args.release, args.threshold)

        run = models.DepMapImportRun(
            release=args.release,
            effect_threshold=str(args.threshold),
            gene_scope=args.genes,
            n_models=n_models,
            n_genes_scanned=n_genes,
            n_dependency_rows=n_rows,
            n_common_essential=sum(1 for s in stats if s in essentials),
            source_files=json.dumps({
                MODEL_FILE: _md5(model_path),
                EFFECT_FILE: _md5(effect_path),
                ESSENTIAL_FILE: _md5(essential_path),
            }, ensure_ascii=False),
        )
        db.add(run)
        db.commit()

        print()
        print("=" * 60)
        print(f"完成。release {args.release}")
        print(f"  細胞株           {n_models}")
        print(f"  掃描基因         {n_genes}")
        print(f"  依賴配對         {n_rows}")
        print(f"  基因摘要         {n_sum}")
        print(f"  其中泛必需基因   {run.n_common_essential}")
        print("=" * 60)
        print()
        print("⚠️ 判讀提醒：依賴配對是**門檻篩選後**的結果，不是完整矩陣。")
        print("   「某基因只有 N 筆」代表達門檻的株數，不是只在 N 株測過——")
        print("   母體請看 depmap_gene_summary.n_lines_total。")
        print()
        print("   泛必需基因的依賴不是抗腫瘤機轉，是細胞毒性，排序時必須排除。")
        print()
        print("   資料來源：DepMap（CC BY 4.0），前端顯示時必須標註出處與釋出版本。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
