import csv
import io
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, require_admin, write_audit_log

router = APIRouter(prefix="/dark-genes", tags=["暗黑基因管理（癌症基因參考資料，目標三）"])


def _yn_to_bool(v: Optional[str]) -> bool:
    return (v or "").strip().lower() == "yes"


# ---------------------------------------------------------------------------
# 前台／一般登入使用者：查詢
# ---------------------------------------------------------------------------

def _build_target_word_index(db: Session):
    """建立「單詞 → 是否有任何 TCMSP 靶點名稱包含這個詞」的索引，
    這樣判斷「1245 個基因裡哪些比對得到靶點」時，每個基因只需要查表，
    不需要每個基因都重新掃過一次全部 1751 個靶點名稱。"""
    all_targets = db.query(models.TcmspTarget.target_name).all()
    word_set = set()
    for (name,) in all_targets:
        word_set |= set(re.findall(r"[A-Za-z0-9]+", (name or "").upper()))
    return word_set


def _gene_has_tcmsp_target(gene: models.DarkGene, target_word_set) -> bool:
    symbols = _gene_symbols_for_match(gene)
    return any(s in target_word_set for s in symbols)


@router.get("/public/list", response_model=List[schemas.DarkGeneOut], summary="（前台）查詢暗黑基因清單（含是否有中藥靶點標記，供查詢站使用）")
def public_list_genes(keyword: Optional[str] = None, gene_type: Optional[str] = None,
                       has_tcmsp_target: Optional[bool] = None,
                       current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(models.DarkGene).filter(models.DarkGene.status == "active")
    if keyword:
        q = q.filter(
            (models.DarkGene.hugo_symbol.ilike(f"%{keyword}%")) |
            (models.DarkGene.gene_aliases.ilike(f"%{keyword}%"))
        )
    if gene_type:
        q = q.filter(models.DarkGene.gene_type == gene_type)
    genes = q.order_by(models.DarkGene.hugo_symbol).all()

    target_word_set = _build_target_word_index(db)
    results = []
    for g in genes:
        out = schemas.DarkGeneOut.model_validate(g)
        out.has_tcmsp_target = _gene_has_tcmsp_target(g, target_word_set)
        if has_tcmsp_target is None or out.has_tcmsp_target == has_tcmsp_target:
            results.append(out)
    return results


# ---------------------------------------------------------------------------
# 後台管理（僅限管理者）：CRUD + 匯入
# ---------------------------------------------------------------------------

@router.get("", response_model=List[schemas.DarkGeneOut], summary="（後台）查詢暗黑基因列表")
def admin_list_genes(keyword: Optional[str] = None, status_filter: Optional[str] = None,
                      gene_type: Optional[str] = None,
                      db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.DarkGene)
    if keyword:
        q = q.filter(
            (models.DarkGene.hugo_symbol.ilike(f"%{keyword}%")) |
            (models.DarkGene.gene_aliases.ilike(f"%{keyword}%"))
        )
    if status_filter:
        q = q.filter(models.DarkGene.status == status_filter)
    if gene_type:
        q = q.filter(models.DarkGene.gene_type == gene_type)
    return q.order_by(models.DarkGene.hugo_symbol).all()


@router.post("", response_model=schemas.DarkGeneOut, summary="（後台）新增暗黑基因")
def create_gene(payload: schemas.DarkGeneCreate, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    if db.query(models.DarkGene).filter(models.DarkGene.hugo_symbol == payload.hugo_symbol).first():
        raise HTTPException(status_code=400, detail="這個基因符號（Hugo Symbol）已存在")
    gene = models.DarkGene(**payload.model_dump())
    db.add(gene)
    db.commit()
    db.refresh(gene)
    write_audit_log(db, admin, "create_dark_gene", "dark_gene", gene.id, f"新增暗黑基因 {gene.hugo_symbol}")
    return gene


@router.put("/{gene_id}", response_model=schemas.DarkGeneOut, summary="（後台）編輯暗黑基因")
def update_gene(gene_id: str, payload: schemas.DarkGeneUpdate, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    gene = db.query(models.DarkGene).filter(models.DarkGene.id == gene_id).first()
    if not gene:
        raise HTTPException(status_code=404, detail="找不到基因資料")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(gene, field, value)
    db.commit()
    db.refresh(gene)
    write_audit_log(db, admin, "update_dark_gene", "dark_gene", gene.id, f"編輯暗黑基因 {gene.hugo_symbol}")
    return gene


@router.delete("/{gene_id}", summary="（後台）刪除暗黑基因（軟刪除）")
def delete_gene(gene_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    gene = db.query(models.DarkGene).filter(models.DarkGene.id == gene_id).first()
    if not gene:
        raise HTTPException(status_code=404, detail="找不到基因資料")
    gene.status = "inactive"
    db.commit()
    write_audit_log(db, admin, "delete_dark_gene_soft", "dark_gene", gene.id, f"刪除（軟刪除）暗黑基因 {gene.hugo_symbol}")
    return {"message": "已刪除（軟刪除）"}


@router.post("/import", summary="（後台）匯入暗黑基因 TSV 檔案（例如 OncoKB 癌症基因列表），依 Hugo Symbol upsert")
async def import_genes(file: UploadFile = File(...), db: Session = Depends(get_db),
                        admin: models.User = Depends(require_admin)):
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="檔案編碼無法解析，請確認是 UTF-8 編碼的 TSV 檔案")

    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    required_cols = {"Hugo Symbol", "Entrez Gene ID", "Gene Type"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"檔案欄位格式不符，至少需要包含：{', '.join(required_cols)}")

    created, updated = 0, 0
    for row in reader:
        symbol = (row.get("Hugo Symbol") or "").strip()
        if not symbol:
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
    write_audit_log(db, admin, "import_dark_genes", "dark_gene", "bulk",
                     f"匯入暗黑基因清單：新增 {created} 筆、更新 {updated} 筆（檔案：{file.filename}）")
    return {"message": "匯入完成", "created": created, "updated": updated}


# ---------------------------------------------------------------------------
# 暗黑基因－靶點關聯：拿基因符號（含別名）去比對 TCMSP 靶點名稱，
# 找出相關的成分／候選藥材。屬於研究輔助功能（機制層級關聯，非臨床療效證據），
# 正式提供醫療建議前仍需要醫師/專業人員審核（詳見 rules.md）。
# ---------------------------------------------------------------------------

def _gene_symbols_for_match(gene: models.DarkGene) -> List[str]:
    symbols = [gene.hugo_symbol.strip().upper()]
    if gene.gene_aliases:
        symbols += [a.strip().upper() for a in gene.gene_aliases.split(",") if a.strip()]
    return symbols


@router.get("/{gene_id}/tcmsp-links", summary="查詢暗黑基因-靶點關聯：比對 TCMSP 靶點名稱，列出候選藥材")
def get_gene_tcmsp_links(gene_id: str, current_user: models.User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    gene = db.query(models.DarkGene).filter(models.DarkGene.id == gene_id).first()
    if not gene:
        raise HTTPException(status_code=404, detail="找不到基因資料")

    symbols = set(_gene_symbols_for_match(gene))
    all_targets = db.query(models.TcmspTarget).all()
    matched_targets = []
    for t in all_targets:
        words = set(re.findall(r"[A-Za-z0-9]+", (t.target_name or "").upper()))
        if words & symbols:
            matched_targets.append(t)

    if not matched_targets:
        return {
            "gene": {"id": gene.id, "hugo_symbol": gene.hugo_symbol, "gene_aliases": gene.gene_aliases},
            "matched_targets": [], "ingredients": [], "herbs": [],
        }

    tar_ids = [t.tar_id for t in matched_targets]
    ingredient_target_rows = db.query(models.TcmspIngredientTarget).filter(
        models.TcmspIngredientTarget.tar_id.in_(tar_ids)
    ).all()
    mol_ids = list({r.mol_id for r in ingredient_target_rows})

    herb_ingredient_rows = db.query(models.TcmspHerbIngredient).filter(
        models.TcmspHerbIngredient.mol_id.in_(mol_ids)
    ).all() if mol_ids else []
    herb_ids = list({r.herb_id for r in herb_ingredient_rows})

    ingredients = db.query(models.TcmspIngredient).filter(models.TcmspIngredient.mol_id.in_(mol_ids)).all() if mol_ids else []
    herbs = db.query(models.TcmspHerb).filter(
        models.TcmspHerb.id.in_(herb_ids), models.TcmspHerb.status == "active"
    ).all() if herb_ids else []

    # 每種藥材附上「透過幾個成分連結到這個基因」的計數，方便排序找出關聯性較強的候選藥材
    mol_to_herbs = {}
    for r in herb_ingredient_rows:
        mol_to_herbs.setdefault(r.mol_id, set()).add(r.herb_id)
    herb_hit_count = {}
    for mol_id in mol_ids:
        for herb_id in mol_to_herbs.get(mol_id, set()):
            herb_hit_count[herb_id] = herb_hit_count.get(herb_id, 0) + 1

    return {
        "gene": {"id": gene.id, "hugo_symbol": gene.hugo_symbol, "gene_aliases": gene.gene_aliases, "gene_type": gene.gene_type},
        "matched_targets": [
            {"tar_id": t.tar_id, "target_name": t.target_name, "drugbank_id": t.drugbank_id, "kegg": t.kegg}
            for t in matched_targets
        ],
        "ingredients": [
            {"mol_id": i.mol_id, "molecule_name": i.molecule_name, "ob": i.ob, "dl": i.dl}
            for i in ingredients
        ],
        "ingredient_target": [{"mol_id": r.mol_id, "tar_id": r.tar_id} for r in ingredient_target_rows],
        "herb_ingredient": [{"herb_id": r.herb_id, "mol_id": r.mol_id} for r in herb_ingredient_rows],
        "herbs": sorted([
            {
                "herb_id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin,
                "herb_en_name": h.herb_en_name, "matched_ingredient_count": herb_hit_count.get(h.id, 0),
            }
            for h in herbs
        ], key=lambda x: -x["matched_ingredient_count"]),
    }
