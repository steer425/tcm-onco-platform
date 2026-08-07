import csv
import io
import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin, write_audit_log

router = APIRouter(prefix="/dna", tags=["DNA 資料匯入與檢測（目標三，研究參考用途）"])


# ---------------------------------------------------------------------------
# 檢體 CRUD
# ---------------------------------------------------------------------------

@router.get("/specimens", response_model=List[schemas.SpecimenOut], summary="查詢檢體列表（可依病患篩選）")
def list_specimens(patient_id: Optional[str] = None, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    q = db.query(models.Specimen)
    if patient_id:
        q = q.filter(models.Specimen.patient_id == patient_id)
    return q.order_by(models.Specimen.created_at.desc()).all()


@router.post("/specimens", response_model=schemas.SpecimenOut, summary="新增檢體")
def create_specimen(payload: schemas.SpecimenCreate, db: Session = Depends(get_db),
                     admin: models.User = Depends(require_admin)):
    if db.query(models.Specimen).filter(models.Specimen.specimen_no == payload.specimen_no).first():
        raise HTTPException(status_code=400, detail="檢體編號已存在")
    if not db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first():
        raise HTTPException(status_code=404, detail="找不到病患資料")
    s = models.Specimen(**payload.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    write_audit_log(db, admin, "create_specimen", "specimen", s.id, f"新增檢體 {s.specimen_no}")
    return s


@router.delete("/specimens/{specimen_id}", summary="刪除檢體（軟刪除）")
def delete_specimen(specimen_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    s = db.query(models.Specimen).filter(models.Specimen.id == specimen_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="找不到檢體資料")
    s.status = "inactive"
    db.commit()
    write_audit_log(db, admin, "delete_specimen_soft", "specimen", s.id, f"刪除（軟刪除）檢體 {s.specimen_no}")
    return {"message": "已刪除（軟刪除）"}


# ---------------------------------------------------------------------------
# 匯入批次 CRUD + 比對暗黑基因
# ---------------------------------------------------------------------------

def _dark_gene_symbol_set(db: Session) -> set:
    return {g.hugo_symbol.upper() for g in db.query(models.DarkGene.hugo_symbol).filter(models.DarkGene.status == "active").all()}


def _variant_to_out(v: models.Variant, dark_symbols: set) -> schemas.VariantOut:
    out = schemas.VariantOut.model_validate(v)
    out.is_dark_gene = bool(v.gene_symbol and v.gene_symbol.upper() in dark_symbols)
    return out


@router.get("/batches", response_model=List[schemas.DnaImportBatchOut], summary="查詢匯入批次列表（可依病患篩選）")
def list_batches(patient_id: Optional[str] = None, db: Session = Depends(get_db),
                  admin: models.User = Depends(require_admin)):
    q = db.query(models.DnaImportBatch)
    if patient_id:
        q = q.filter(models.DnaImportBatch.patient_id == patient_id)
    return q.order_by(models.DnaImportBatch.created_at.desc()).all()


@router.post("/batches", response_model=schemas.DnaImportBatchOut, summary="新增匯入批次（直接以結構化資料建立，含變異清單）")
def create_batch(payload: schemas.DnaImportBatchCreate, db: Session = Depends(get_db),
                  admin: models.User = Depends(require_admin)):
    if db.query(models.DnaImportBatch).filter(models.DnaImportBatch.batch_no == payload.batch_no).first():
        raise HTTPException(status_code=400, detail="批次編號已存在")
    if not db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first():
        raise HTTPException(status_code=404, detail="找不到病患資料")

    data = payload.model_dump()
    variants_data = data.pop("variants")
    batch = models.DnaImportBatch(**data, source_type="import", imported_by=admin.id, variant_count=len(variants_data))
    db.add(batch)
    db.flush()
    for v in variants_data:
        db.add(models.Variant(**v, batch_id=batch.id, patient_id=payload.patient_id))
    db.commit()
    db.refresh(batch)
    write_audit_log(db, admin, "create_dna_batch", "dna_import_batch", batch.id,
                     f"新增 DNA 匯入批次 {batch.batch_no}（{len(variants_data)} 筆變異）")
    return batch


@router.post("/batches/upload", response_model=schemas.DnaImportBatchOut, summary="上傳 CSV 檔案匯入 DNA 變異資料")
async def upload_batch(patient_id: str, batch_no: str, specimen_id: Optional[str] = None,
                        platform: Optional[str] = None, panel: Optional[str] = None,
                        file: UploadFile = File(...), db: Session = Depends(get_db),
                        admin: models.User = Depends(require_admin)):
    if not db.query(models.Patient).filter(models.Patient.id == patient_id).first():
        raise HTTPException(status_code=404, detail="找不到病患資料")
    if db.query(models.DnaImportBatch).filter(models.DnaImportBatch.batch_no == batch_no).first():
        raise HTTPException(status_code=400, detail="批次編號已存在")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="檔案編碼無法解析，請確認是 UTF-8 編碼的 CSV 檔案")

    reader = csv.DictReader(io.StringIO(text))
    required_cols = {"chromosome", "position", "ref_allele", "alt_allele", "gene_symbol"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"CSV 欄位格式不符，至少需要包含：{', '.join(required_cols)}")

    rows = list(reader)
    batch = models.DnaImportBatch(
        batch_no=batch_no, patient_id=patient_id, specimen_id=specimen_id,
        source_type="import", source_filename=file.filename, platform=platform, panel=panel,
        imported_by=admin.id, variant_count=len(rows),
    )
    db.add(batch)
    db.flush()
    for row in rows:
        db.add(models.Variant(
            batch_id=batch.id, patient_id=patient_id,
            chromosome=(row.get("chromosome") or "").strip() or None,
            position=(row.get("position") or "").strip() or None,
            ref_allele=(row.get("ref_allele") or "").strip() or None,
            alt_allele=(row.get("alt_allele") or "").strip() or None,
            gene_symbol=(row.get("gene_symbol") or "").strip() or None,
            hgvs=(row.get("hgvs") or "").strip() or None,
            depth=int(row["depth"]) if (row.get("depth") or "").strip().isdigit() else None,
            allele_fraction=(row.get("allele_fraction") or "").strip() or None,
            qc_status=(row.get("qc_status") or "").strip() or None,
            clinical_significance=(row.get("clinical_significance") or "").strip() or None,
        ))
    db.commit()
    db.refresh(batch)
    write_audit_log(db, admin, "upload_dna_batch", "dna_import_batch", batch.id,
                     f"上傳 DNA 資料匯入批次 {batch.batch_no}（{len(rows)} 筆變異，檔案：{file.filename}）")
    return batch


@router.delete("/batches/{batch_id}", summary="刪除匯入批次（軟刪除）")
def delete_batch(batch_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    b = db.query(models.DnaImportBatch).filter(models.DnaImportBatch.id == batch_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="找不到批次資料")
    b.status = "inactive"
    db.commit()
    write_audit_log(db, admin, "delete_dna_batch_soft", "dna_import_batch", b.id, f"刪除（軟刪除）批次 {b.batch_no}")
    return {"message": "已刪除（軟刪除）"}


@router.get("/batches/{batch_id}/variants", response_model=List[schemas.VariantOut], summary="查詢某批次的變異清單（含是否命中暗黑基因標記）")
def list_batch_variants(batch_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    variants = db.query(models.Variant).filter(models.Variant.batch_id == batch_id).all()
    dark_symbols = _dark_gene_symbol_set(db)
    return [_variant_to_out(v, dark_symbols) for v in variants]


@router.get("/patients/{patient_id}/compare", summary="多次匯入比較：同一病患不同批次之間變異的異同")
def compare_batches(patient_id: str, batch_ids: str, db: Session = Depends(get_db),
                     admin: models.User = Depends(require_admin)):
    """batch_ids 是逗號分隔的批次 id 清單，例如 ?batch_ids=id1,id2,id3"""
    ids = [b.strip() for b in batch_ids.split(",") if b.strip()]
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要選擇 2 個批次才能比較")

    batches = db.query(models.DnaImportBatch).filter(
        models.DnaImportBatch.id.in_(ids), models.DnaImportBatch.patient_id == patient_id
    ).all()
    if len(batches) != len(ids):
        raise HTTPException(status_code=404, detail="有批次不存在或不屬於這位病患")

    dark_symbols = _dark_gene_symbol_set(db)
    batch_variant_keys = {}  # batch_id -> {(chromosome,position,ref,alt): variant}
    for b in batches:
        variants = db.query(models.Variant).filter(models.Variant.batch_id == b.id).all()
        batch_variant_keys[b.id] = {
            (v.chromosome, v.position, v.ref_allele, v.alt_allele): v for v in variants
        }

    all_keys = set()
    for keys in batch_variant_keys.values():
        all_keys |= set(keys.keys())

    rows = []
    for key in all_keys:
        row = {"chromosome": key[0], "position": key[1], "ref_allele": key[2], "alt_allele": key[3], "presence": {}}
        gene_symbol = None
        for b in batches:
            v = batch_variant_keys[b.id].get(key)
            row["presence"][b.id] = v is not None
            if v and v.gene_symbol:
                gene_symbol = v.gene_symbol
        row["gene_symbol"] = gene_symbol
        row["is_dark_gene"] = bool(gene_symbol and gene_symbol.upper() in dark_symbols)
        row["in_all_batches"] = all(row["presence"].values())
        rows.append(row)

    rows.sort(key=lambda r: (not r["is_dark_gene"], not r["in_all_batches"], r["chromosome"] or ""))

    return {
        "patient_id": patient_id,
        "batches": [{"id": b.id, "batch_no": b.batch_no, "created_at": b.created_at, "variant_count": b.variant_count} for b in batches],
        "variants": rows,
    }


# ---------------------------------------------------------------------------
# DNA 測試資料產生（合成測試資料，可選多人、可選是否含暗黑基因變異）
# ---------------------------------------------------------------------------

_RANDOM_GENE_SYMBOLS = ["FOO1", "BAR2", "BAZ3", "QUX4", "TEST5"]  # 非暗黑基因，純粹當作背景雜訊變異
_CHROMOSOMES = [str(i) for i in range(1, 23)] + ["X", "Y"]


@router.post("/test-data/generate", summary="（後台）DNA 測試資料產生：選擇多位病患，可勾選是否含暗黑基因變異")
def generate_test_dna_data(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    patient_ids = payload.get("patient_ids") or []
    include_dark_genes = bool(payload.get("include_dark_genes", True))
    variants_per_patient = int(payload.get("variants_per_patient", 8))
    dark_gene_ratio = float(payload.get("dark_gene_ratio", 0.4))  # 產生的變異裡，大約幾成命中暗黑基因

    if not patient_ids:
        raise HTTPException(status_code=400, detail="請至少選擇一位病患")

    patients = db.query(models.Patient).filter(models.Patient.id.in_(patient_ids)).all()
    if len(patients) != len(patient_ids):
        raise HTTPException(status_code=404, detail="有病患不存在")

    dark_gene_symbols = [g.hugo_symbol for g in db.query(models.DarkGene.hugo_symbol).filter(models.DarkGene.status == "active").all()]

    created_batches = []
    for p in patients:
        batch_no = f"TEST-DNA-{p.patient_id}-{random.randint(10000,99999)}"
        n_dark = int(variants_per_patient * dark_gene_ratio) if include_dark_genes and dark_gene_symbols else 0
        n_random = variants_per_patient - n_dark

        batch = models.DnaImportBatch(
            batch_no=batch_no, patient_id=p.id, source_type="synthetic",
            source_filename=None, platform="測試資料產生（合成）", panel="TEST-PANEL",
            reference_genome="GRCh38", pipeline_info="synthetic-generator-v1",
            imported_by=admin.id, variant_count=variants_per_patient,
            notes="系統產生的測試資料，非真實病患檢測結果",
        )
        db.add(batch)
        db.flush()

        chosen_dark_genes = random.sample(dark_gene_symbols, min(n_dark, len(dark_gene_symbols))) if n_dark else []
        for gene in chosen_dark_genes:
            db.add(models.Variant(
                batch_id=batch.id, patient_id=p.id,
                chromosome=random.choice(_CHROMOSOMES), position=str(random.randint(100000, 200000000)),
                ref_allele=random.choice("ACGT"), alt_allele=random.choice("ACGT"),
                gene_symbol=gene, hgvs=f"c.{random.randint(1,3000)}{random.choice('ACGT')}>{random.choice('ACGT')}",
                depth=random.randint(30, 300), allele_fraction=f"{random.uniform(0.05,0.95):.2f}",
                qc_status="pass", notes="測試資料",
            ))
        for _ in range(n_random):
            db.add(models.Variant(
                batch_id=batch.id, patient_id=p.id,
                chromosome=random.choice(_CHROMOSOMES), position=str(random.randint(100000, 200000000)),
                ref_allele=random.choice("ACGT"), alt_allele=random.choice("ACGT"),
                gene_symbol=random.choice(_RANDOM_GENE_SYMBOLS), hgvs=f"c.{random.randint(1,3000)}{random.choice('ACGT')}>{random.choice('ACGT')}",
                depth=random.randint(30, 300), allele_fraction=f"{random.uniform(0.05,0.95):.2f}",
                qc_status="pass", notes="測試資料",
            ))
        created_batches.append(batch)

    db.commit()
    write_audit_log(db, admin, "generate_test_dna_data", "dna_import_batch", "bulk",
                     f"為 {len(patients)} 位病患產生測試 DNA 資料（每人 {variants_per_patient} 筆變異）")
    return {
        "message": "已產生測試資料",
        "batches": [{"id": b.id, "batch_no": b.batch_no, "patient_id": b.patient_id, "variant_count": b.variant_count} for b in created_batches],
    }


# ---------------------------------------------------------------------------
# 病患暗黑基因摘要 + 建議候選中藥（機制層級研究參考，非醫療建議）
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}/dark-gene-summary", summary="查詢病患的暗黑基因命中摘要（跨所有批次，去重）")
def patient_dark_gene_summary(patient_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="找不到病患資料")

    dark_genes_by_symbol = {g.hugo_symbol.upper(): g for g in db.query(models.DarkGene).filter(models.DarkGene.status == "active").all()}

    variants = db.query(models.Variant).join(models.DnaImportBatch).filter(
        models.Variant.patient_id == patient_id, models.DnaImportBatch.status == "active"
    ).all()

    matched = {}  # gene symbol -> {gene info, variant_count}
    for v in variants:
        if v.gene_symbol and v.gene_symbol.upper() in dark_genes_by_symbol:
            g = dark_genes_by_symbol[v.gene_symbol.upper()]
            if g.hugo_symbol not in matched:
                matched[g.hugo_symbol] = {
                    "hugo_symbol": g.hugo_symbol, "gene_type": g.gene_type, "id": g.id, "variant_count": 0,
                }
            matched[g.hugo_symbol]["variant_count"] += 1

    results = sorted(matched.values(), key=lambda x: -x["variant_count"])
    return {
        "patient_id": patient_id, "patient_name": patient.name,
        "total_variants": len(variants), "dark_gene_count": len(results),
        "dark_genes": results,
    }


@router.get("/patients/ranking", summary="（後台）病患暗黑基因統計排行：哪位病患帶有的暗黑基因數量最高")
def patient_dark_gene_ranking(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    dark_symbols = _dark_gene_symbol_set(db)
    patients = db.query(models.Patient).filter(models.Patient.status == "active").all()

    results = []
    for p in patients:
        variants = db.query(models.Variant).join(models.DnaImportBatch).filter(
            models.Variant.patient_id == p.id, models.DnaImportBatch.status == "active"
        ).all()
        matched_symbols = {v.gene_symbol.upper() for v in variants if v.gene_symbol and v.gene_symbol.upper() in dark_symbols}
        if not matched_symbols:
            continue
        results.append({
            "patient_id": p.id, "patient_display_id": p.patient_id, "patient_name": p.name,
            "dark_gene_count": len(matched_symbols), "total_variants": len(variants),
            "gene_symbols": sorted(matched_symbols),
        })

    results.sort(key=lambda r: -r["dark_gene_count"])
    return {"total": len(results), "patients": results}
