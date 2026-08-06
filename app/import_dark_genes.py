"""
匯入暗黑基因（癌症基因參考資料）TSV 檔案，例如 OncoKB 癌症基因列表。

使用方式：
    python -m app.import_dark_genes data_import/cancer_gene_list.tsv

依 Hugo Symbol 做 upsert（已存在就更新，不存在就新增），可重複執行，
不會清空重建整張表（跟 TCMSP 資料匯入的「先清空再匯入」不同，
因為暗黑基因清單之後可能會有使用者透過後台介面手動新增/編輯的資料，
清空重建會把這些手動資料一併洗掉）。
"""
import csv
import sys

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal, engine, Base


def _yn_to_bool(v):
    return (v or "").strip().lower() == "yes"


def import_data(tsv_path: str):
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        with open(tsv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter="\t")
            created, updated, skipped = 0, 0, 0
            for row in reader:
                symbol = (row.get("Hugo Symbol") or "").strip()
                if not symbol:
                    skipped += 1
                    continue
                existing = db.query(models.DarkGene).filter(models.DarkGene.hugo_symbol == symbol).first()
                fields = {
                    "entrez_gene_id": (row.get("Entrez Gene ID") or "").strip() or None,
                    "grch37_isoform": (row.get("GRCh37 Isoform") or "").strip() or None,
                    "grch37_refseq": (row.get("GRCh37 RefSeq") or "").strip() or None,
                    "grch38_isoform": (row.get("GRCh38 Isoform") or "").strip() or None,
                    "grch38_refseq": (row.get("GRCh38 RefSeq") or "").strip() or None,
                    "gene_type": (row.get("Gene Type") or "").strip() or None,
                    "occurrence_count": int(row["# of occurrence within resources (Column K-P)"])
                        if (row.get("# of occurrence within resources (Column K-P)") or "").strip().isdigit() else None,
                    "oncokb_annotated": _yn_to_bool(row.get("OncoKB Annotated")),
                    "msk_impact": _yn_to_bool(row.get("MSK-IMPACT")),
                    "msk_heme": _yn_to_bool(row.get("MSK-HEME")),
                    "foundation_one": _yn_to_bool(row.get("FOUNDATION ONE")),
                    "foundation_one_heme": _yn_to_bool(row.get("FOUNDATION ONE HEME")),
                    "vogelstein": _yn_to_bool(row.get("Vogelstein")),
                    "cosmic_cgc": _yn_to_bool(row.get("COSMIC CGC (v99)")),
                    "gene_aliases": (row.get("Gene Aliases") or "").strip() or None,
                }
                if existing:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    updated += 1
                else:
                    db.add(models.DarkGene(hugo_symbol=symbol, **fields))
                    created += 1
            db.commit()
        print(f"完成！新增 {created} 筆、更新 {updated} 筆、略過 {skipped} 筆（無基因符號的空白列）。")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("使用方式：python -m app.import_dark_genes data_import/cancer_gene_list.tsv")
        sys.exit(1)
    import_data(sys.argv[1])
