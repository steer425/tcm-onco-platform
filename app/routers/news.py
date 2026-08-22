"""每日重點新聞 — 前台 API（一般登入使用者）。

定位：科研輔助情報彙整，不作為醫療診斷或治療建議。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.database import get_db, get_query_db
from app.deps import get_current_user, has_permission
from app.news.service import get_settings, loads, taipei_today

router = APIRouter(prefix="/news", tags=["每日重點新聞"])


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------
def _entity_link(e: models.NewsArticleEntity) -> Optional[str]:
    """把實體轉成查詢站連結。靶點目前沒有專屬查詢頁，改由前端開彈窗（見 /news/targets/{tar_id}）。"""
    if e.entity_type == models.NewsEntityType.herb and e.herb_id is not None:
        return f"tcmsp_query.html?herb={e.herb_id}"
    if e.entity_type == models.NewsEntityType.disease and e.dis_id:
        return f"disease_query.html?dis={e.dis_id}"
    return None


def _to_article(a: models.NewsArticle, src: models.NewsSource,
                entities: list[models.NewsArticleEntity],
                is_bookmarked: bool = False, bookmark_count: int = 0,
                admin: bool = False) -> dict:
    out = {
        "id": a.id,
        "title": a.title,
        "title_zh": a.title_zh,
        "summary_zh": a.summary_zh,
        "key_points": loads(a.key_points, []),
        "caveat_zh": a.caveat_zh,
        "url": a.url,
        "external_id": a.external_id,
        "doi": a.doi,
        "journal": a.journal,
        "authors": a.authors,
        "study_design": a.study_design,
        "evidence_level": a.evidence_level.value if a.evidence_level else None,
        "evidence_maturity": a.evidence_maturity.value if a.evidence_maturity else "unknown",
        "cancer_types": loads(a.cancer_types, []),
        "intervention_types": loads(a.intervention_types, []),
        "tags": loads(a.tags, []),
        "is_safety_signal": bool(a.is_safety_signal),
        # 一般使用者拿到的清單本來就已經在查詢階段濾掉未解禁文章（見 get_daily/get_archive
        # 的 can_view_embargoed 判斷），所以這裡不分權限一律回傳這個欄位是安全的——
        # 沒權限的人本來就收不到 is_embargoed=True 的那一列，這個欄位只是讓有權限
        # 提前看到的人，在畫面上知道「這篇是提前存取」而已。
        "is_embargoed": bool(a.is_embargoed),
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "collected_at": a.collected_at.isoformat() if a.collected_at else None,
        "rank_score": float(a.rank_score or 0),
        "source": {
            "slug": src.slug, "name_zh": src.name_zh, "name_en": src.name_en,
            "homepage": src.homepage,
            "evidence_level": src.evidence_level.value if src.evidence_level else None,
        },
        "entities": [
            {
                "type": e.entity_type.value,
                "key": e.entity_key,
                "name": e.display_name,
                "matched_text": e.matched_text,
                "link": _entity_link(e),
                "herb_id": e.herb_id,
                "tar_id": e.tar_id,
                "dis_id": e.dis_id,
                "mol_id": e.mol_id,
            }
            for e in entities
        ],
        "is_bookmarked": is_bookmarked,
        "bookmark_count": bookmark_count,
    }
    if admin:
        out.update({
            "status": a.status.value if a.status else None,
            "is_deleted": bool(a.is_deleted),
            "deleted_at": a.deleted_at.isoformat() if a.deleted_at else None,
            "deleted_by": a.deleted_by,
            "delete_note": a.delete_note,
            "relevance_score": float(a.relevance_score or 0),
            "embargo_until": a.embargo_until.isoformat() if a.embargo_until else None,
        })
    return out


def _load_related(query_db: Session, db: Session, article_ids: list[str], user_id: str):
    """一次撈齊實體、收藏數、個人收藏狀態，避免 N+1 查詢。

    entities 是新聞內文的參考資料（已納入唯讀模式本機快取），走 query_db；
    收藏數／個人收藏狀態綁 users 外鍵，不進快取，一律走 db（見 app/local_cache.py）。
    未走快取分流的呼叫端（例如 /news/bookmarks）對 query_db／db 傳同一個 session 即可。
    """
    if not article_ids:
        return {}, {}, set()

    ents: dict[str, list] = {}
    for e in (query_db.query(models.NewsArticleEntity)
              .filter(models.NewsArticleEntity.article_id.in_(article_ids)).all()):
        ents.setdefault(e.article_id, []).append(e)

    counts: dict[str, int] = {}
    for aid, cnt in (db.query(models.UserNewsBookmark.article_id,
                              func.count(models.UserNewsBookmark.id))
                     .filter(models.UserNewsBookmark.article_id.in_(article_ids))
                     .group_by(models.UserNewsBookmark.article_id).all()):
        counts[aid] = cnt

    mine = {r[0] for r in db.query(models.UserNewsBookmark.article_id)
            .filter(models.UserNewsBookmark.user_id == user_id,
                    models.UserNewsBookmark.article_id.in_(article_ids)).all()}
    return ents, counts, mine


# ---------------------------------------------------------------------------
# 每日重點新聞
# ---------------------------------------------------------------------------
@router.get("/daily", summary="（前台）取得每日重點新聞（預設 10 篇）")
def get_daily(
    date: Optional[str] = Query(None, description="YYYY-MM-DD，預設今天（Asia/Taipei）"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),               # 帳號/收藏/模組設定：一律連遠端，不進唯讀快取
    query_db: Session = Depends(get_query_db),    # 新聞內文/來源/每日精選：唯讀模式下可讀本機端快取
):
    target = date if (date and len(date) == 10) else taipei_today()
    can_view_embargoed = has_permission(db, current_user, "F0-20")

    exists = (query_db.query(models.NewsDailyDigest.article_id)
              .filter(models.NewsDailyDigest.digest_date == target).first())
    if not exists:
        # 該日尚未產生（例如 04:00 排程還沒跑）→ 回退到最近一個有資料的日期
        fallback = (query_db.query(models.NewsDailyDigest.digest_date)
                    .filter(models.NewsDailyDigest.digest_date <= target)
                    .order_by(models.NewsDailyDigest.digest_date.desc()).first())
        if not fallback:
            settings = get_settings(db)
            return {"digest_date": target, "total": 0, "items": [],
                    "disclaimer": settings["disclaimer_zh"],
                    "generated_at": None, "available_dates": []}
        target = fallback[0]

    query = (query_db.query(models.NewsDailyDigest, models.NewsArticle, models.NewsSource)
            .join(models.NewsArticle, models.NewsArticle.id == models.NewsDailyDigest.article_id)
            .join(models.NewsSource, models.NewsSource.id == models.NewsArticle.source_id)
            .filter(models.NewsDailyDigest.digest_date == target,
                    models.NewsArticle.is_deleted.is_(False)))
    if not can_view_embargoed:
        query = query.filter(or_(models.NewsArticle.is_embargoed.is_(False),
                                  models.NewsArticle.embargo_until <= datetime.utcnow()))
    rows = query.order_by(models.NewsDailyDigest.is_pinned.desc(),
                          models.NewsDailyDigest.rank.asc()).all()

    ids = [a.id for _, a, _ in rows]
    ents, counts, mine = _load_related(query_db, db, ids, current_user.id)

    items = []
    for d, a, s in rows:
        item = _to_article(a, s, ents.get(a.id, []),
                           is_bookmarked=a.id in mine,
                           bookmark_count=counts.get(a.id, 0))
        item.update({"rank": d.rank, "is_pinned": bool(d.is_pinned),
                     "pick_reason": d.pick_reason})
        items.append(item)

    dates = [r[0] for r in (query_db.query(models.NewsDailyDigest.digest_date).distinct()
                            .order_by(models.NewsDailyDigest.digest_date.desc()).limit(30).all())]
    generated = (query_db.query(models.NewsDailyDigest.created_at)
                 .filter(models.NewsDailyDigest.digest_date == target)
                 .order_by(models.NewsDailyDigest.created_at.asc()).first())

    return {
        "digest_date": target,
        "total": len(items),
        "items": items,
        "disclaimer": get_settings(db)["disclaimer_zh"],
        "generated_at": generated[0].isoformat() if generated and generated[0] else None,
        "available_dates": dates,
    }


@router.get("/archive", summary="（前台）歷史新聞瀏覽")
def get_archive(
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    source: Optional[str] = None,
    cancer_type: Optional[str] = None,
    safety_only: bool = False,
    q: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),               # 帳號/收藏：一律連遠端，不進唯讀快取
    query_db: Session = Depends(get_query_db),    # 新聞內文/來源：唯讀模式下可讀本機端快取
):
    can_view_embargoed = has_permission(db, current_user, "F0-20")
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = (query_db.query(models.NewsArticle, models.NewsSource)
             .join(models.NewsSource, models.NewsSource.id == models.NewsArticle.source_id)
             .filter(models.NewsArticle.is_deleted.is_(False),
                     models.NewsArticle.collected_at >= cutoff))
    if not can_view_embargoed:
        query = query.filter(or_(models.NewsArticle.is_embargoed.is_(False),
                                  models.NewsArticle.embargo_until <= datetime.utcnow()))
    if source:
        query = query.filter(models.NewsSource.slug == source)
    if safety_only:
        query = query.filter(models.NewsArticle.is_safety_signal.is_(True))
    if cancer_type:
        # cancer_types 是 JSON 陣列字串，用 LIKE 比對即可（資料量小）
        query = query.filter(models.NewsArticle.cancer_types.like(f'%"{cancer_type}"%'))
    if q:
        query = query.filter(models.NewsArticle.search_blob.like(f"%{q.lower()}%"))

    rows = query.order_by(models.NewsArticle.rank_score.desc()).limit(limit).all()
    ids = [a.id for a, _ in rows]
    ents, counts, mine = _load_related(query_db, db, ids, current_user.id)

    return {
        "total": len(rows),
        "items": [_to_article(a, s, ents.get(a.id, []),
                              is_bookmarked=a.id in mine,
                              bookmark_count=counts.get(a.id, 0))
                  for a, s in rows],
    }


@router.get("/sources", summary="（前台）啟用中的權威來源清單")
def list_sources(current_user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_query_db)):
    rows = (db.query(models.NewsSource)
            .filter(models.NewsSource.is_enabled.is_(True))
            .order_by(models.NewsSource.slug).all())
    return [{"slug": s.slug, "name_zh": s.name_zh, "name_en": s.name_en,
             "homepage": s.homepage,
             "evidence_level": s.evidence_level.value if s.evidence_level else None,
             "notes": s.notes} for s in rows]


@router.get("/targets/{tar_id}", summary="（前台）靶點詳情：關聯藥材與疾病（新聞實體彈窗用）")
def get_target_detail(tar_id: str,
                      current_user: models.User = Depends(get_current_user),
                      db: Session = Depends(get_query_db)):
    """靶點目前沒有專屬查詢站頁面，新聞卡片點擊靶點標籤時改開彈窗顯示這裡的資料。"""
    target = db.query(models.TcmspTarget).filter(models.TcmspTarget.tar_id == tar_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="找不到此靶點")

    herbs = (db.query(models.TcmspHerb.id, models.TcmspHerb.herb_cn_name,
                      models.TcmspHerb.herb_en_name)
             .join(models.TcmspHerbIngredient,
                   models.TcmspHerbIngredient.herb_id == models.TcmspHerb.id)
             .join(models.TcmspIngredientTarget,
                   models.TcmspIngredientTarget.mol_id == models.TcmspHerbIngredient.mol_id)
             .filter(models.TcmspIngredientTarget.tar_id == tar_id,
                     models.TcmspHerb.status == "active")
             .distinct().limit(40).all())

    diseases = (db.query(models.TcmspDisease.dis_id, models.TcmspDisease.disease_name,
                         models.TcmspDisease.disease_cn_name)
                .join(models.TcmspTargetDisease,
                      models.TcmspTargetDisease.dis_id == models.TcmspDisease.dis_id)
                .filter(models.TcmspTargetDisease.tar_id == tar_id)
                .distinct().limit(40).all())

    return {
        "tar_id": target.tar_id,
        "target_name": target.target_name,
        "drugbank_id": target.drugbank_id,
        "kegg": target.kegg,
        "herbs": [{"herb_id": h.id, "name": h.herb_cn_name or h.herb_en_name,
                   "link": f"tcmsp_query.html?herb={h.id}"} for h in herbs],
        "diseases": [{"dis_id": d.dis_id, "name": d.disease_cn_name or d.disease_name,
                      "link": f"disease_query.html?dis={d.dis_id}"} for d in diseases],
    }


# ---------------------------------------------------------------------------
# 個人保留（勾選保留）
# ---------------------------------------------------------------------------
class BookmarkIn(BaseModel):
    article_id: str
    folder: str = Field(default="default", max_length=128)
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/bookmarks", summary="（前台）勾選保留新聞")
def add_bookmark(payload: BookmarkIn,
                 current_user: models.User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    article = (db.query(models.NewsArticle)
               .filter(models.NewsArticle.id == payload.article_id).first())
    if not article or article.is_deleted:
        raise HTTPException(status_code=404, detail="找不到這則新聞")

    row = (db.query(models.UserNewsBookmark)
           .filter(models.UserNewsBookmark.user_id == current_user.id,
                   models.UserNewsBookmark.article_id == payload.article_id).first())
    if row:
        row.folder = payload.folder
        if payload.note is not None:
            row.note = payload.note
    else:
        row = models.UserNewsBookmark(user_id=current_user.id,
                                      article_id=payload.article_id,
                                      folder=payload.folder, note=payload.note)
        db.add(row)
    db.commit()

    count = (db.query(models.UserNewsBookmark)
             .filter(models.UserNewsBookmark.article_id == payload.article_id).count())
    return {"ok": True, "article_id": payload.article_id,
            "folder": row.folder, "note": row.note, "bookmark_count": count}


@router.delete("/bookmarks/{article_id}", summary="（前台）取消保留")
def remove_bookmark(article_id: str,
                    current_user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    row = (db.query(models.UserNewsBookmark)
           .filter(models.UserNewsBookmark.user_id == current_user.id,
                   models.UserNewsBookmark.article_id == article_id).first())
    if not row:
        raise HTTPException(status_code=404, detail="尚未保留這則新聞")
    db.delete(row)
    db.commit()
    return {"ok": True, "article_id": article_id}


@router.get("/bookmarks", summary="（前台）我的保留新聞")
def list_bookmarks(folder: Optional[str] = None, q: Optional[str] = None,
                   page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   current_user: models.User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    query = (db.query(models.UserNewsBookmark, models.NewsArticle, models.NewsSource)
             .join(models.NewsArticle,
                   models.NewsArticle.id == models.UserNewsBookmark.article_id)
             .join(models.NewsSource, models.NewsSource.id == models.NewsArticle.source_id)
             .filter(models.UserNewsBookmark.user_id == current_user.id))
    if folder:
        query = query.filter(models.UserNewsBookmark.folder == folder)
    if q:
        query = query.filter(models.NewsArticle.search_blob.like(f"%{q.lower()}%"))

    total = query.count()
    rows = (query.order_by(models.UserNewsBookmark.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size).all())

    ids = [a.id for _, a, _ in rows]
    # 個人收藏清單本身就是使用者資料，不走唯讀快取分流，query_db/db 傳同一個 session
    ents, counts, _ = _load_related(db, db, ids, current_user.id)

    folders = [r[0] for r in (db.query(models.UserNewsBookmark.folder).distinct()
                              .filter(models.UserNewsBookmark.user_id == current_user.id).all())]

    return {
        "total": total, "page": page, "page_size": page_size, "folders": folders,
        "items": [{
            "bookmark_id": b.id,
            "folder": b.folder,
            "note": b.note,
            "bookmarked_at": b.created_at.isoformat() if b.created_at else None,
            # 管理者軟刪除的文章仍保留在收藏中，前端據此標示「已由管理者移除」
            "article_removed": bool(a.is_deleted),
            "article": _to_article(a, s, ents.get(a.id, []), is_bookmarked=True,
                                   bookmark_count=counts.get(a.id, 0)),
        } for b, a, s in rows],
        "disclaimer": get_settings(db)["disclaimer_zh"],
    }
