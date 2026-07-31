from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, require_admin, write_audit_log

router = APIRouter(tags=["目標五：中藥行地理推薦"])


def _pharmacy_to_out(p: models.Pharmacy) -> schemas.PharmacyOut:
    reviews = p.reviews
    avg = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None
    return schemas.PharmacyOut(
        id=p.id, name=p.name, address=p.address, phone=p.phone,
        business_hours=p.business_hours, description=p.description,
        latitude=float(p.latitude), longitude=float(p.longitude),
        status=p.status, notes=p.notes, avg_rating=avg, review_count=len(reviews),
        created_at=p.created_at,
    )


def _review_to_out(r: models.PharmacyReview) -> schemas.PharmacyReviewOut:
    out = schemas.PharmacyReviewOut.model_validate(r)
    out.account = r.user.account if r.user else None
    return out


# =========================================================
# 後台管理（僅限管理者）：中藥行資料 CRUD + 評價管理
# =========================================================

@router.get("/pharmacies", response_model=List[schemas.PharmacyOut], summary="（後台）查詢中藥行列表")
def admin_list_pharmacies(keyword: Optional[str] = None, db: Session = Depends(get_db),
                           admin: models.User = Depends(require_admin)):
    q = db.query(models.Pharmacy)
    if keyword:
        q = q.filter(models.Pharmacy.name.ilike(f"%{keyword}%"))
    return [_pharmacy_to_out(p) for p in q.order_by(models.Pharmacy.created_at.desc()).all()]


@router.post("/pharmacies", response_model=schemas.PharmacyOut, summary="（後台）新增中藥行")
def admin_create_pharmacy(payload: schemas.PharmacyCreate, db: Session = Depends(get_db),
                           admin: models.User = Depends(require_admin)):
    p = models.Pharmacy(
        name=payload.name, address=payload.address, phone=payload.phone,
        business_hours=payload.business_hours, description=payload.description,
        latitude=str(payload.latitude), longitude=str(payload.longitude),
        notes=payload.notes,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    write_audit_log(db, admin, "create_pharmacy", "pharmacy", p.id, f"新增中藥行 {p.name}")
    return _pharmacy_to_out(p)


@router.put("/pharmacies/{pharmacy_id}", response_model=schemas.PharmacyOut, summary="（後台）編輯中藥行")
def admin_update_pharmacy(pharmacy_id: str, payload: schemas.PharmacyUpdate, db: Session = Depends(get_db),
                           admin: models.User = Depends(require_admin)):
    p = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    data = payload.model_dump(exclude_unset=True)
    for field in ["name", "address", "phone", "business_hours", "description", "notes", "status"]:
        if field in data and data[field] is not None:
            setattr(p, field, data[field])
    if "latitude" in data and data["latitude"] is not None:
        p.latitude = str(data["latitude"])
    if "longitude" in data and data["longitude"] is not None:
        p.longitude = str(data["longitude"])
    db.commit()
    db.refresh(p)
    write_audit_log(db, admin, "update_pharmacy", "pharmacy", p.id, f"編輯中藥行 {p.name}")
    return _pharmacy_to_out(p)


@router.delete("/pharmacies/{pharmacy_id}", summary="（後台）刪除中藥行（軟刪除：下架）")
def admin_delete_pharmacy(pharmacy_id: str, db: Session = Depends(get_db),
                           admin: models.User = Depends(require_admin)):
    p = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    p.status = models.PharmacyStatus.inactive
    db.commit()
    write_audit_log(db, admin, "delete_pharmacy_soft", "pharmacy", p.id, f"下架（軟刪除）中藥行 {p.name}")
    return {"message": "已下架（軟刪除）"}


@router.get("/pharmacies/{pharmacy_id}/reviews", response_model=List[schemas.PharmacyReviewOut],
            summary="（後台）查詢某中藥行的所有評價（含管理備注）")
def admin_list_reviews(pharmacy_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    reviews = db.query(models.PharmacyReview).filter(models.PharmacyReview.pharmacy_id == pharmacy_id).all()
    return [_review_to_out(r) for r in reviews]


@router.put("/pharmacy-reviews/{review_id}/notes", response_model=schemas.PharmacyReviewOut,
            summary="（後台）補充評價管理備注")
def admin_update_review_notes(review_id: str, payload: schemas.PharmacyReviewNoteUpdate,
                               db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    r = db.query(models.PharmacyReview).filter(models.PharmacyReview.id == review_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="找不到評價")
    r.notes = payload.notes
    db.commit()
    db.refresh(r)
    return _review_to_out(r)


@router.delete("/pharmacy-reviews/{review_id}", summary="（後台）刪除不當評價")
def admin_delete_review(review_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    r = db.query(models.PharmacyReview).filter(models.PharmacyReview.id == review_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="找不到評價")
    db.delete(r)
    db.commit()
    write_audit_log(db, admin, "delete_pharmacy_review", "pharmacy_review", review_id, "後台刪除不當評價")
    return {"message": "已刪除"}


# =========================================================
# 前台（一般登入使用者皆可使用）：中藥行地理推薦 + 評價
# =========================================================

@router.get("/public/pharmacies", response_model=List[schemas.PharmacyOut],
            summary="（前台）查詢上架中的中藥行列表（供地理推薦排序使用）")
def public_list_pharmacies(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(models.Pharmacy).filter(models.Pharmacy.status == models.PharmacyStatus.active)
    return [_pharmacy_to_out(p) for p in q.all()]


@router.get("/public/pharmacies/{pharmacy_id}", response_model=schemas.PharmacyOut, summary="（前台）中藥行詳情")
def public_get_pharmacy(pharmacy_id: str, current_user: models.User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    p = db.query(models.Pharmacy).filter(
        models.Pharmacy.id == pharmacy_id, models.Pharmacy.status == models.PharmacyStatus.active
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    return _pharmacy_to_out(p)


@router.get("/public/pharmacies/{pharmacy_id}/reviews", response_model=List[schemas.PharmacyReviewOut],
            summary="（前台）查詢某中藥行的公開評價")
def public_list_reviews(pharmacy_id: str, current_user: models.User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    reviews = db.query(models.PharmacyReview).filter(models.PharmacyReview.pharmacy_id == pharmacy_id).all()
    return [_review_to_out(r) for r in reviews]


@router.post("/public/pharmacies/{pharmacy_id}/reviews", response_model=schemas.PharmacyReviewOut,
             summary="（前台）新增我對此中藥行的評價（每人每店限一則）")
def public_create_review(pharmacy_id: str, payload: schemas.PharmacyReviewCreate,
                          current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    pharmacy = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not pharmacy:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    existing = db.query(models.PharmacyReview).filter(
        models.PharmacyReview.pharmacy_id == pharmacy_id, models.PharmacyReview.user_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="您已經評價過這間中藥行，請使用編輯功能")
    review = models.PharmacyReview(
        pharmacy_id=pharmacy_id, user_id=current_user.id,
        rating=payload.rating, comment=payload.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    write_audit_log(db, current_user, "create_pharmacy_review", "pharmacy_review", review.id,
                     f"{current_user.account} 評價 {pharmacy.name}：{payload.rating} 星")
    return _review_to_out(review)


@router.put("/public/reviews/{review_id}", response_model=schemas.PharmacyReviewOut, summary="（前台）編輯我自己的評價")
def public_update_review(review_id: str, payload: schemas.PharmacyReviewUpdate,
                          current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    review = db.query(models.PharmacyReview).filter(
        models.PharmacyReview.id == review_id, models.PharmacyReview.user_id == current_user.id
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="找不到您的評價紀錄")
    if payload.rating is not None:
        review.rating = payload.rating
    if payload.comment is not None:
        review.comment = payload.comment
    db.commit()
    db.refresh(review)
    return _review_to_out(review)


@router.delete("/public/reviews/{review_id}", summary="（前台）刪除我自己的評價")
def public_delete_review(review_id: str, current_user: models.User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    review = db.query(models.PharmacyReview).filter(
        models.PharmacyReview.id == review_id, models.PharmacyReview.user_id == current_user.id
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="找不到您的評價紀錄")
    db.delete(review)
    db.commit()
    return {"message": "已刪除"}
