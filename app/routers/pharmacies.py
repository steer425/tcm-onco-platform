from datetime import datetime, time as dt_time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, require_admin, write_audit_log

router = APIRouter(tags=["目標五：中藥行地理推薦"])

# 熱門程度計算權重（純粹是合理的預設值，之後有實際使用數據可以再調整）
POPULARITY_WEIGHTS = {"view": 1, "favorite": 3, "share": 2, "nav_click": 2, "checkin": 4}
# 加權評分：貝式平均，C 是「虛擬的先驗評價數」，評價數愈少愈會被拉向全站平均，避免只有 1 則五星就衝到第一名
BAYESIAN_PRIOR_COUNT = 5
GLOBAL_AVG_RATING_FALLBACK = 4.0


def _parse_hhmm(s):
    if not s:
        return None
    try:
        h, m = s.strip().split(":")
        return dt_time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def _business_status(opens_at, closes_at, now=None):
    """判斷營業狀態：open / closing_soon（30分鐘內打烊）/ opening_soon（30分鐘內開門）/ closed / unknown"""
    open_t, close_t = _parse_hhmm(opens_at), _parse_hhmm(closes_at)
    if not open_t or not close_t:
        return "unknown"
    now = now or datetime.now()
    now_t = now.time()
    now_minutes = now_t.hour * 60 + now_t.minute
    open_minutes = open_t.hour * 60 + open_t.minute
    close_minutes = close_t.hour * 60 + close_t.minute

    if open_minutes <= close_minutes:  # 同一天內營業（不跨午夜）
        if open_minutes <= now_minutes < close_minutes:
            return "closing_soon" if (close_minutes - now_minutes) <= 30 else "open"
        if 0 <= (open_minutes - now_minutes) <= 30:
            return "opening_soon"
        return "closed"
    else:  # 跨午夜營業（例如 22:00-02:00）
        if now_minutes >= open_minutes or now_minutes < close_minutes:
            remaining = (close_minutes - now_minutes) if now_minutes < close_minutes else (close_minutes + 1440 - now_minutes)
            return "closing_soon" if remaining <= 30 else "open"
        if 0 <= (open_minutes - now_minutes) <= 30:
            return "opening_soon"
        return "closed"


def _pharmacy_to_out(p: models.Pharmacy, stats: dict, current_user_id: str = None, favorited_ids: set = None) -> schemas.PharmacyOut:
    reviews = p.reviews
    total_stars = sum(r.rating for r in reviews)
    avg = round(total_stars / len(reviews), 1) if reviews else None
    weighted = round(
        (total_stars + BAYESIAN_PRIOR_COUNT * GLOBAL_AVG_RATING_FALLBACK) / (len(reviews) + BAYESIAN_PRIOR_COUNT), 2
    ) if (reviews or BAYESIAN_PRIOR_COUNT) else None

    s = stats.get(p.id, {})
    checkin_count = s.get("checkin_count", 0)
    my_checkin_count = s.get("my_checkin_count", 0)
    avg_spending = s.get("avg_spending")

    popularity = (
        p.view_count * POPULARITY_WEIGHTS["view"]
        + p.favorite_count * POPULARITY_WEIGHTS["favorite"]
        + p.share_count * POPULARITY_WEIGHTS["share"]
        + p.nav_click_count * POPULARITY_WEIGHTS["nav_click"]
        + checkin_count * POPULARITY_WEIGHTS["checkin"]
    )

    return schemas.PharmacyOut(
        id=p.id, name=p.name, address=p.address, phone=p.phone,
        business_hours=p.business_hours, opens_at=p.opens_at, closes_at=p.closes_at,
        description=p.description,
        latitude=float(p.latitude), longitude=float(p.longitude),
        status=p.status, notes=p.notes, avg_rating=avg, review_count=len(reviews),
        weighted_rating=weighted, total_stars=total_stars,
        checkin_count=checkin_count, my_checkin_count=my_checkin_count, avg_spending=avg_spending,
        view_count=p.view_count, favorite_count=p.favorite_count, share_count=p.share_count,
        nav_click_count=p.nav_click_count, popularity_score=popularity,
        business_status=_business_status(p.opens_at, p.closes_at),
        opening_date=p.opening_date, discount_percent=p.discount_percent,
        discount_description=p.discount_description, discount_valid_until=p.discount_valid_until,
        is_favorited=(p.id in favorited_ids) if favorited_ids else False,
        created_at=p.created_at,
    )


def _build_stats(db: Session, pharmacy_ids: list, current_user_id: str = None) -> dict:
    """一次算完所有藥局的打卡次數/平均消費，避免每間店各自查一次資料庫"""
    if not pharmacy_ids:
        return {}
    stats = {}
    rows = db.query(
        models.PharmacyCheckin.pharmacy_id,
        func.count(models.PharmacyCheckin.id),
        func.avg(models.PharmacyCheckin.spending_amount),
    ).filter(models.PharmacyCheckin.pharmacy_id.in_(pharmacy_ids)).group_by(models.PharmacyCheckin.pharmacy_id).all()
    for pid, cnt, avg_spend in rows:
        stats[pid] = {"checkin_count": cnt, "avg_spending": round(avg_spend, 0) if avg_spend else None}

    if current_user_id:
        my_rows = db.query(
            models.PharmacyCheckin.pharmacy_id, func.count(models.PharmacyCheckin.id)
        ).filter(
            models.PharmacyCheckin.pharmacy_id.in_(pharmacy_ids), models.PharmacyCheckin.user_id == current_user_id
        ).group_by(models.PharmacyCheckin.pharmacy_id).all()
        for pid, cnt in my_rows:
            stats.setdefault(pid, {})["my_checkin_count"] = cnt

    return stats


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
    pharmacies = q.order_by(models.Pharmacy.created_at.desc()).all()
    stats = _build_stats(db, [p.id for p in pharmacies], admin.id)
    return [_pharmacy_to_out(p, stats, admin.id) for p in pharmacies]


@router.post("/pharmacies", response_model=schemas.PharmacyOut, summary="（後台）新增中藥行")
def admin_create_pharmacy(payload: schemas.PharmacyCreate, db: Session = Depends(get_db),
                           admin: models.User = Depends(require_admin)):
    p = models.Pharmacy(
        name=payload.name, address=payload.address, phone=payload.phone,
        business_hours=payload.business_hours, opens_at=payload.opens_at, closes_at=payload.closes_at,
        description=payload.description,
        latitude=str(payload.latitude), longitude=str(payload.longitude),
        notes=payload.notes, opening_date=payload.opening_date,
        discount_percent=payload.discount_percent, discount_description=payload.discount_description,
        discount_valid_until=payload.discount_valid_until,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    write_audit_log(db, admin, "create_pharmacy", "pharmacy", p.id, f"新增中藥行 {p.name}")
    return _pharmacy_to_out(p, {}, admin.id)


@router.put("/pharmacies/{pharmacy_id}", response_model=schemas.PharmacyOut, summary="（後台）編輯中藥行")
def admin_update_pharmacy(pharmacy_id: str, payload: schemas.PharmacyUpdate, db: Session = Depends(get_db),
                           admin: models.User = Depends(require_admin)):
    p = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    data = payload.model_dump(exclude_unset=True)
    for field in ["name", "address", "phone", "business_hours", "opens_at", "closes_at", "description", "notes",
                  "status", "opening_date", "discount_percent", "discount_description", "discount_valid_until"]:
        if field in data and data[field] is not None:
            setattr(p, field, data[field])
    if "latitude" in data and data["latitude"] is not None:
        p.latitude = str(data["latitude"])
    if "longitude" in data and data["longitude"] is not None:
        p.longitude = str(data["longitude"])
    db.commit()
    db.refresh(p)
    write_audit_log(db, admin, "update_pharmacy", "pharmacy", p.id, f"編輯中藥行 {p.name}")
    stats = _build_stats(db, [p.id], admin.id)
    return _pharmacy_to_out(p, stats, admin.id)


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
            summary="（前台）查詢上架中的中藥行列表，支援多種排序模式")
def public_list_pharmacies(sort: Optional[str] = None, keyword: Optional[str] = None,
                            rating_mode: Optional[str] = "weighted", checkin_scope: Optional[str] = "all",
                            price_order: Optional[str] = "asc",
                            current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    sort 可選：distance（前端依定位計算，這裡不處理）／rating／checkin／popularity／
    business_status／price／discount／newest／personalized／relevance
    rating_mode：total（總星等）／average（平均星等）／weighted（加權星等，預設）
    checkin_scope：all（全部使用者）／mine（只看我自己）
    price_order：asc（低到高）／desc（高到低）
    keyword：用於「相關程度」排序時，比對店名/地址/描述
    """
    q = db.query(models.Pharmacy).filter(models.Pharmacy.status == models.PharmacyStatus.active)
    pharmacies = q.all()
    stats = _build_stats(db, [p.id for p in pharmacies], current_user.id)
    favorited_ids = {f.pharmacy_id for f in db.query(models.PharmacyFavorite).filter(models.PharmacyFavorite.user_id == current_user.id).all()}

    results = [_pharmacy_to_out(p, stats, current_user.id, favorited_ids) for p in pharmacies]

    if sort == "rating":
        key_field = {"total": "total_stars", "average": "avg_rating", "weighted": "weighted_rating"}.get(rating_mode, "weighted_rating")
        results.sort(key=lambda x: (getattr(x, key_field) if getattr(x, key_field) is not None else -1), reverse=True)
    elif sort == "checkin":
        key_field = "my_checkin_count" if checkin_scope == "mine" else "checkin_count"
        results.sort(key=lambda x: getattr(x, key_field), reverse=True)
    elif sort == "popularity":
        results.sort(key=lambda x: x.popularity_score, reverse=True)
    elif sort == "business_status":
        status_priority = {"open": 0, "closing_soon": 1, "opening_soon": 1, "closed": 2, "unknown": 3}
        results.sort(key=lambda x: status_priority.get(x.business_status, 3))
    elif sort == "price":
        with_price = [r for r in results if r.avg_spending is not None]
        without_price = [r for r in results if r.avg_spending is None]
        with_price.sort(key=lambda x: x.avg_spending, reverse=(price_order == "desc"))
        results = with_price + without_price
    elif sort == "discount":
        results.sort(key=lambda x: (x.discount_percent is None, -(x.discount_percent or 0)))
    elif sort == "newest":
        results.sort(key=lambda x: x.opening_date or x.created_at.strftime("%Y-%m-%d"), reverse=True)
    elif sort == "personalized":
        # 簡易個人化推薦：以「我收藏過/打卡過的店」為訊號，優先顯示尚未收藏但熱門度高的店（探索），
        # 其次是我已經收藏的店（方便快速回訪）。這是簡化的規則式排序，不是完整的協同過濾/機器學習模型。
        results.sort(key=lambda x: (not x.is_favorited, -x.popularity_score, -(x.weighted_rating or 0)))
    elif sort == "relevance" and keyword:
        kw = keyword.strip().lower()
        def relevance_score(p):
            score = 0
            if kw in (p.name or "").lower():
                score += 10
            if kw in (p.description or "").lower():
                score += 5
            if kw in (p.address or "").lower():
                score += 3
            return score
        results = [r for r in results if relevance_score(r) > 0]
        results.sort(key=relevance_score, reverse=True)

    return results


@router.get("/public/pharmacies/{pharmacy_id}", response_model=schemas.PharmacyOut, summary="（前台）中藥行詳情")
def public_get_pharmacy(pharmacy_id: str, current_user: models.User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    p = db.query(models.Pharmacy).filter(
        models.Pharmacy.id == pharmacy_id, models.Pharmacy.status == models.PharmacyStatus.active
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    stats = _build_stats(db, [p.id], current_user.id)
    favorited_ids = {f.pharmacy_id for f in db.query(models.PharmacyFavorite).filter(models.PharmacyFavorite.user_id == current_user.id).all()}
    return _pharmacy_to_out(p, stats, current_user.id, favorited_ids)


@router.post("/public/pharmacies/{pharmacy_id}/view", summary="（前台）記錄一次瀏覽（供熱門程度統計）")
def track_view(pharmacy_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    p.view_count += 1
    db.commit()
    return {"view_count": p.view_count}


@router.post("/public/pharmacies/{pharmacy_id}/share", summary="（前台）記錄一次分享（供熱門程度統計）")
def track_share(pharmacy_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    p.share_count += 1
    db.commit()
    return {"share_count": p.share_count}


@router.post("/public/pharmacies/{pharmacy_id}/navigate", summary="（前台）記錄一次路線規劃/導航點擊（供熱門程度統計），並回傳可直接開啟的地圖導航連結")
def track_navigate(pharmacy_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    p.nav_click_count += 1
    db.commit()
    nav_url = f"https://www.openstreetmap.org/directions?to={p.latitude}%2C{p.longitude}"
    return {"nav_click_count": p.nav_click_count, "navigation_url": nav_url}


@router.post("/public/pharmacies/{pharmacy_id}/checkin", response_model=schemas.PharmacyCheckinOut,
             summary="（前台）打卡（可選填本次消費金額）")
def create_checkin(pharmacy_id: str, payload: schemas.PharmacyCheckinCreate,
                    current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    checkin = models.PharmacyCheckin(
        pharmacy_id=pharmacy_id, user_id=current_user.id,
        spending_amount=payload.spending_amount, notes=payload.notes,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)
    out = schemas.PharmacyCheckinOut.model_validate(checkin)
    out.account = current_user.account
    return out


@router.get("/public/pharmacies/{pharmacy_id}/checkins", response_model=List[schemas.PharmacyCheckinOut],
            summary="（前台）查詢某中藥行的打卡紀錄")
def list_checkins(pharmacy_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    checkins = db.query(models.PharmacyCheckin).filter(models.PharmacyCheckin.pharmacy_id == pharmacy_id).order_by(
        models.PharmacyCheckin.created_at.desc()
    ).all()
    results = []
    for c in checkins:
        out = schemas.PharmacyCheckinOut.model_validate(c)
        out.account = c.user.account if c.user else None
        results.append(out)
    return results


@router.post("/public/pharmacies/{pharmacy_id}/favorite", summary="（前台）收藏這間中藥行")
def add_favorite(pharmacy_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    existing = db.query(models.PharmacyFavorite).filter(
        models.PharmacyFavorite.pharmacy_id == pharmacy_id, models.PharmacyFavorite.user_id == current_user.id
    ).first()
    if not existing:
        db.add(models.PharmacyFavorite(pharmacy_id=pharmacy_id, user_id=current_user.id))
        p.favorite_count += 1
        db.commit()
    return {"message": "已收藏", "favorite_count": p.favorite_count}


@router.delete("/public/pharmacies/{pharmacy_id}/favorite", summary="（前台）取消收藏")
def remove_favorite(pharmacy_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(models.Pharmacy).filter(models.Pharmacy.id == pharmacy_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="找不到中藥行資料")
    existing = db.query(models.PharmacyFavorite).filter(
        models.PharmacyFavorite.pharmacy_id == pharmacy_id, models.PharmacyFavorite.user_id == current_user.id
    ).first()
    if existing:
        db.delete(existing)
        p.favorite_count = max(0, p.favorite_count - 1)
        db.commit()
    return {"message": "已取消收藏", "favorite_count": p.favorite_count}


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
