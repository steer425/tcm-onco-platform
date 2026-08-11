import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db, get_query_db
from app.deps import get_current_user, require_admin, write_audit_log

router = APIRouter(prefix="/gencc-diseases", tags=["可編碼蛋白區疾病與中藥關聯（GenCC 基因-疾病關聯資料）"])


# ---------------------------------------------------------------------------
# 前台／一般登入使用者：查詢
# ---------------------------------------------------------------------------

@router.get("/public/list", response_model=List[schemas.GenccDiseaseOut],
            summary="（前台）查詢 GenCC 可編碼蛋白區疾病清單（含是否有中藥靶點標記，為預先計算好的統計欄位，供查詢站使用）")
def public_list_diseases(keyword: Optional[str] = None, classification: Optional[str] = None,
                          has_tcmsp_target: Optional[bool] = None,
                          current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db)):
    q = db.query(models.GenccDisease).filter(models.GenccDisease.status == "active")
    if keyword:
        q = q.filter(
            (models.GenccDisease.gene_symbol.ilike(f"%{keyword}%")) |
            (models.GenccDisease.disease_title.ilike(f"%{keyword}%")) |
            (models.GenccDisease.disease_cn_name.ilike(f"%{keyword}%"))
        )
    if classification:
        q = q.filter(models.GenccDisease.classification_title == classification)
    if has_tcmsp_target is not None:
        q = q.filter(models.GenccDisease.has_tcmsp_target == has_tcmsp_target)
    diseases = q.order_by(models.GenccDisease.gene_symbol).all()
    return [schemas.GenccDiseaseOut.model_validate(d) for d in diseases]


@router.get("/public/stats", summary="（前台）GenCC 疾病統計：依信心等級（classification）分組，統計有/沒有比對到 TCMSP 靶點的筆數")
def public_get_stats(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_query_db)):
    diseases = db.query(models.GenccDisease).filter(models.GenccDisease.status == "active").all()
    groups: dict = {}
    for d in diseases:
        key = d.classification_title or "（未分類）"
        g = groups.setdefault(key, {"classification": key, "total": 0, "with_target": 0})
        g["total"] += 1
        if d.has_tcmsp_target:
            g["with_target"] += 1
    total = len(diseases)
    with_target = sum(1 for d in diseases if d.has_tcmsp_target)
    return {"total": total, "with_target": with_target, "groups": sorted(groups.values(), key=lambda x: -x["total"])}


@router.get("/herb-links/{herb_id}", summary="查詢藥材-GenCC疾病關聯：這個藥材的成分連結到哪些靶點，再比對出哪些可編碼蛋白區疾病（畫面比照「藥材與暗黑基因關聯」）")
def get_herb_gencc_links(herb_id: int, current_user: models.User = Depends(get_current_user),
                          db: Session = Depends(get_query_db)):
    herb = db.query(models.TcmspHerb).filter(models.TcmspHerb.id == herb_id, models.TcmspHerb.status == "active").first()
    if not herb:
        raise HTTPException(status_code=404, detail="找不到藥材資料")

    herb_ingredient_rows = db.query(models.TcmspHerbIngredient).filter(models.TcmspHerbIngredient.herb_id == herb_id).all()
    mol_ids = [r.mol_id for r in herb_ingredient_rows]

    ingredient_target_rows = db.query(models.TcmspIngredientTarget).filter(
        models.TcmspIngredientTarget.mol_id.in_(mol_ids)
    ).all() if mol_ids else []
    tar_ids = list({r.tar_id for r in ingredient_target_rows})

    ingredients = db.query(models.TcmspIngredient).filter(models.TcmspIngredient.mol_id.in_(mol_ids)).all() if mol_ids else []
    targets = db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id.in_(tar_ids)).all() if tar_ids else []

    # 建立「基因符號 -> 符合的 GenCC 疾病」索引，避免每個靶點都重新掃一次全部資料
    # （GenCC 資料量遠大於暗黑基因，這個索引的重要性更高）
    all_diseases = db.query(models.GenccDisease).filter(models.GenccDisease.status == "active").all()
    symbol_to_diseases = {}
    for d in all_diseases:
        symbol_to_diseases.setdefault((d.gene_symbol or "").upper(), []).append(d)

    target_disease_matches = {}  # tar_id -> [disease, ...]
    all_matched_diseases = {}  # disease.id -> {disease info, matched_target_ids: set()}
    for t in targets:
        words = set(re.findall(r"[A-Za-z0-9]+", (t.target_name or "").upper()))
        matched = []
        for w in words:
            matched.extend(symbol_to_diseases.get(w, []))
        target_disease_matches[t.tar_id] = matched
        for d in matched:
            if d.id not in all_matched_diseases:
                all_matched_diseases[d.id] = {
                    "id": d.id, "gene_symbol": d.gene_symbol, "disease_title": d.disease_title,
                    "disease_cn_name": d.disease_cn_name, "classification_title": d.classification_title,
                    "moi_title": d.moi_title, "matched_target_ids": set(),
                }
            all_matched_diseases[d.id]["matched_target_ids"].add(t.tar_id)

    target_disease_edges = []
    for tar_id, diseases in target_disease_matches.items():
        for d in diseases:
            target_disease_edges.append({"tar_id": tar_id, "disease_id": d.id})

    return {
        "herb": {
            "herb_id": herb.id, "herb_cn_name": herb.herb_cn_name, "herb_pinyin": herb.herb_pinyin,
            "herb_en_name": herb.herb_en_name,
        },
        "ingredients": [
            {"mol_id": i.mol_id, "molecule_name": i.molecule_name, "ob": i.ob, "dl": i.dl}
            for i in ingredients
        ],
        "targets": [
            {
                "tar_id": t.tar_id, "target_name": t.target_name, "drugbank_id": t.drugbank_id,
                "matched_diseases": [
                    {"id": d.id, "gene_symbol": d.gene_symbol, "disease_title": d.disease_title}
                    for d in target_disease_matches.get(t.tar_id, [])
                ],
            }
            for t in targets
        ],
        "herb_ingredient": [{"herb_id": r.herb_id, "mol_id": r.mol_id} for r in herb_ingredient_rows],
        "ingredient_target": [{"mol_id": r.mol_id, "tar_id": r.tar_id} for r in ingredient_target_rows],
        "target_disease": target_disease_edges,
        "matched_diseases": sorted([
            {
                "id": v["id"], "gene_symbol": v["gene_symbol"], "disease_title": v["disease_title"],
                "disease_cn_name": v["disease_cn_name"], "classification_title": v["classification_title"],
                "moi_title": v["moi_title"], "matched_target_count": len(v["matched_target_ids"]),
            }
            for v in all_matched_diseases.values()
        ], key=lambda x: -x["matched_target_count"]),
    }


@router.get("/public/herb-stats", summary="（前台）中藥可編碼蛋白區疾病覆蓋統計：以藥材為主，列出每種藥材連結到幾個不重複的 GenCC 疾病（統計數字為預先計算好的資料庫欄位）")
def public_get_herb_stats(only_with_disease: bool = True, current_user: models.User = Depends(get_current_user),
                           db: Session = Depends(get_query_db)):
    q = db.query(models.TcmspHerb).filter(models.TcmspHerb.status == "active")
    if only_with_disease:
        q = q.filter(models.TcmspHerb.gencc_disease_count > 0)
    herbs = q.order_by(models.TcmspHerb.gencc_disease_count.desc(), models.TcmspHerb.herb_cn_name).all()
    return {"total": len(herbs), "herbs": [
        {"herb_id": h.id, "herb_cn_name": h.herb_cn_name, "herb_pinyin": h.herb_pinyin, "herb_en_name": h.herb_en_name,
         "gencc_disease_count": h.gencc_disease_count}
        for h in herbs
    ]}


# ---------------------------------------------------------------------------
# 後台：CRUD／匯入
# ---------------------------------------------------------------------------

@router.get("", response_model=List[schemas.GenccDiseaseOut], summary="（後台）查詢 GenCC 疾病清單（含 inactive）")
def admin_list_diseases(keyword: Optional[str] = None, classification: Optional[str] = None,
                         db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.GenccDisease)
    if keyword:
        q = q.filter(
            (models.GenccDisease.gene_symbol.ilike(f"%{keyword}%")) |
            (models.GenccDisease.disease_title.ilike(f"%{keyword}%")) |
            (models.GenccDisease.disease_cn_name.ilike(f"%{keyword}%"))
        )
    if classification:
        q = q.filter(models.GenccDisease.classification_title == classification)
    diseases = q.order_by(models.GenccDisease.gene_symbol).limit(500).all()
    return [schemas.GenccDiseaseOut.model_validate(d) for d in diseases]


@router.post("", response_model=schemas.GenccDiseaseOut, summary="（後台）手動新增一筆 GenCC 疾病資料")
def create_disease(payload: schemas.GenccDiseaseCreate, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    if db.query(models.GenccDisease).filter(models.GenccDisease.sgc_id == payload.sgc_id).first():
        raise HTTPException(status_code=400, detail="這個 sgc_id 已經存在")
    disease = models.GenccDisease(**payload.model_dump())
    db.add(disease)
    db.commit()
    db.refresh(disease)
    write_audit_log(db, admin, "create_gencc_disease", "gencc_disease", disease.id, f"新增 GenCC 疾病資料 {disease.sgc_id}")
    return schemas.GenccDiseaseOut.model_validate(disease)


@router.put("/{disease_id}", response_model=schemas.GenccDiseaseOut, summary="（後台）編輯 GenCC 疾病資料（常用於補充中文名稱）")
def update_disease(disease_id: str, payload: schemas.GenccDiseaseUpdate, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    disease = db.query(models.GenccDisease).filter(models.GenccDisease.id == disease_id).first()
    if not disease:
        raise HTTPException(status_code=404, detail="找不到資料")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(disease, k, v)
    db.commit()
    db.refresh(disease)
    write_audit_log(db, admin, "update_gencc_disease", "gencc_disease", disease.id, f"編輯 GenCC 疾病資料 {disease.sgc_id}")
    return schemas.GenccDiseaseOut.model_validate(disease)


@router.delete("/{disease_id}", summary="（後台）軟刪除 GenCC 疾病資料（設為 inactive，不會真的從資料庫移除）")
def delete_disease(disease_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    disease = db.query(models.GenccDisease).filter(models.GenccDisease.id == disease_id).first()
    if not disease:
        raise HTTPException(status_code=404, detail="找不到資料")
    disease.status = "inactive"
    db.commit()
    write_audit_log(db, admin, "delete_gencc_disease", "gencc_disease", disease.id, f"刪除 GenCC 疾病資料 {disease.sgc_id}")
    return {"message": "已刪除"}
