"""
匯入 GenCC（Gene Curation Coalition）基因-疾病關聯資料，來源：https://thegencc.org/download

使用方式：
    python -m app.import_gencc_diseases data_import/gencc-submissions.csv

下載方式（使用者自行操作，這支腳本不會自動下載）：
    到 https://thegencc.org/download 頁面，選「RECOMMENDED New Format」下的 CSV 連結
    （網址：https://thegencc.org/download/action/submissions-export-csv?format=new），
    存成 data_import/gencc-submissions.csv 再執行這支腳本。

資料量遠大於暗黑基因（GenCC 完整資料集通常有 1.5~2 萬筆斷言），依 sgc_id 做 upsert
（已存在就更新，不存在就新增），可重複執行，不會清空重建整張表——
理由跟 import_dark_genes.py 一樣：之後可能會有使用者透過後台介面手動編輯/補充中文名稱，
清空重建會把這些手動資料一併洗掉。

匯入完成後會自動觸發 app/recompute_stats.py 重算 has_tcmsp_target 等統計欄位。
"""
import csv
import sys

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal, engine, Base


def import_data(csv_path: str):
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        created, updated, skipped = 0, 0, 0
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            batch = []
            for i, row in enumerate(reader, start=1):
                sgc_id = (row.get("sgc_id") or "").strip()
                gene_symbol = (row.get("gene_symbol") or "").strip()
                if not sgc_id or not gene_symbol:
                    skipped += 1
                    continue

                fields = {
                    "version_number": (row.get("version_number") or "").strip() or None,
                    "gene_curie": (row.get("gene_curie") or "").strip() or None,
                    "gene_symbol": gene_symbol,
                    "disease_curie": (row.get("disease_curie") or "").strip() or None,
                    "disease_title": (row.get("disease_title") or "").strip() or None,
                    "disease_original_curie": (row.get("disease_original_curie") or "").strip() or None,
                    "disease_original_title": (row.get("disease_original_title") or "").strip() or None,
                    "classification_curie": (row.get("classification_curie") or "").strip() or None,
                    "classification_title": (row.get("classification_title") or "").strip() or None,
                    "moi_curie": (row.get("moi_curie") or "").strip() or None,
                    "moi_title": (row.get("moi_title") or "").strip() or None,
                    "submitter_title": (row.get("submitter_title") or "").strip() or None,
                    "submitted_as_pmids": (row.get("submitted_as_pmids") or "").strip() or None,
                }

                existing = db.query(models.GenccDisease).filter(models.GenccDisease.sgc_id == sgc_id).first()
                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    updated += 1
                else:
                    db.add(models.GenccDisease(sgc_id=sgc_id, **fields))
                    created += 1

                # 每 2000 筆 commit 一次，避免一次塞進單一交易造成記憶體/效能問題
                # （GenCC 資料量比暗黑基因大 10 倍以上，不能照搬「全部讀完才 commit」的做法）
                if (created + updated) % 2000 == 0:
                    db.commit()
                    print(f"  已處理 {created + updated} 筆...")

            db.commit()
        print(f"完成！新增 {created} 筆、更新 {updated} 筆、略過 {skipped} 筆（缺少 sgc_id 或 gene_symbol 的列）。")

        print("\n開始重算統計欄位（GenCC 疾病的中藥靶點比對結果、藥材靶點/基因統計）...")
        from app.recompute_stats import recompute_all_stats
        recompute_all_stats(db)
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("使用方式：python -m app.import_gencc_diseases data_import/gencc-submissions.csv")
        sys.exit(1)
    import_data(sys.argv[1])
