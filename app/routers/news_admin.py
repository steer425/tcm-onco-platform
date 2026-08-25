"""每日重點新聞 — 後台 API（管理者群組）。

併入「公告管理」頁面的分頁呈現，權限代碼 F0-19。
管理者操作一律寫進全站現成的 AuditLog（write_audit_log），不另建稽核表。
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import get_current_user, require_admin, write_audit_log
from app.news import discover, keywords as news_keywords, short_summary
from app.news.service import (
    backfill_summaries, dumps, get_settings, loads, run_daily_collection, set_setting,
    sync_sources,
)
from app.routers.news import _to_article

router = APIRouter(prefix="/news/admin", tags=["每日重點新聞－後台管理"])

# 爬蟲設定（NewsSource.config）裡可能存有出站用的憑證（例如 PubMed api_key）。
# 這些不是入站驗證用的共享密鑰（compare_digest 那套是給 /collect/scheduled 這種
# 免登入端點防時序攻擊用的，這裡不適用），但一樣不該在任何回應或稽核紀錄裡明碼外洩。
_SENSITIVE_CONFIG_KEYS = {"api_key", "apikey", "secret", "token", "password"}


def _redact_config(config: dict) -> dict:
    return {k: ("********" if k.lower() in _SENSITIVE_CONFIG_KEYS and v else v)
            for k, v in config.items()}


# ---------------------------------------------------------------------------
# 查詢
# ---------------------------------------------------------------------------
class ArticleQuery(BaseModel):
    q: Optional[str] = None
    source_slugs: Optional[list[str]] = None
    evidence_levels: Optional[list[str]] = None
    cancer_types: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    is_safety_signal: Optional[bool] = None
    status: Optional[Literal["active", "archived", "deleted"]] = None
    include_deleted: bool = False
    only_deleted: bool = False
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    in_digest: Optional[bool] = None
    bookmarked_only: bool = False
    sort: Literal["collected_desc", "published_desc", "rank_desc"] = "collected_desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


@router.post("/articles/search", summary="（後台）查詢新聞（可查已刪除）")
def search_articles(payload: ArticleQuery,
                    current_user: models.User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    query = (db.query(models.NewsArticle, models.NewsSource)
             .join(models.NewsSource, models.NewsSource.id == models.NewsArticle.source_id))

    if payload.only_deleted:
        query = query.filter(models.NewsArticle.is_deleted.is_(True))
    elif not payload.include_deleted:
        query = query.filter(models.NewsArticle.is_deleted.is_(False))

    if payload.q:
        query = query.filter(models.NewsArticle.search_blob.like(f"%{payload.q.lower()}%"))
    if payload.source_slugs:
        query = query.filter(models.NewsSource.slug.in_(payload.source_slugs))
    if payload.evidence_levels:
        query = query.filter(models.NewsArticle.evidence_level.in_(payload.evidence_levels))
    if payload.is_safety_signal is not None:
        query = query.filter(models.NewsArticle.is_safety_signal.is_(payload.is_safety_signal))
    if payload.status:
        query = query.filter(models.NewsArticle.status == payload.status)
    if payload.cancer_types:
        from sqlalchemy import or_
        query = query.filter(or_(*[models.NewsArticle.cancer_types.like(f'%"{c}"%')
                                   for c in payload.cancer_types]))
    if payload.tags:
        from sqlalchemy import or_
        query = query.filter(or_(*[models.NewsArticle.tags.like(f'%"{t}"%')
                                   for t in payload.tags]))
    if payload.date_from:
        query = query.filter(models.NewsArticle.collected_at >= f"{payload.date_from} 00:00:00")
    if payload.date_to:
        query = query.filter(models.NewsArticle.collected_at <= f"{payload.date_to} 23:59:59")
    if payload.in_digest is True:
        query = query.filter(models.NewsArticle.id.in_(
            db.query(models.NewsDailyDigest.article_id)))
    elif payload.in_digest is False:
        query = query.filter(~models.NewsArticle.id.in_(
            db.query(models.NewsDailyDigest.article_id)))
    if payload.bookmarked_only:
        query = query.filter(models.NewsArticle.id.in_(
            db.query(models.UserNewsBookmark.article_id)))

    total = query.count()

    order = {
        "collected_desc": models.NewsArticle.collected_at.desc(),
        "published_desc": models.NewsArticle.published_at.desc(),
        "rank_desc": models.NewsArticle.rank_score.desc(),
    }[payload.sort]
    rows = (query.order_by(order)
            .offset((payload.page - 1) * payload.page_size)
            .limit(payload.page_size).all())

    ids = [a.id for a, _ in rows]
    ents: dict[str, list] = {}
    counts: dict[str, int] = {}
    digest_dates: dict[str, list[str]] = {}
    if ids:
        for e in (db.query(models.NewsArticleEntity)
                  .filter(models.NewsArticleEntity.article_id.in_(ids)).all()):
            ents.setdefault(e.article_id, []).append(e)
        for aid, c in (db.query(models.UserNewsBookmark.article_id,
                                func.count(models.UserNewsBookmark.id))
                       .filter(models.UserNewsBookmark.article_id.in_(ids))
                       .group_by(models.UserNewsBookmark.article_id).all()):
            counts[aid] = c
        for aid, d in (db.query(models.NewsDailyDigest.article_id,
                                models.NewsDailyDigest.digest_date)
                       .filter(models.NewsDailyDigest.article_id.in_(ids))
                       .order_by(models.NewsDailyDigest.digest_date.desc()).all()):
            digest_dates.setdefault(aid, []).append(d)

    items = []
    for a, s in rows:
        item = _to_article(a, s, ents.get(a.id, []),
                           bookmark_count=counts.get(a.id, 0), admin=True)
        item["in_digest_dates"] = digest_dates.get(a.id, [])
        items.append(item)

    facets = {
        "by_status": dict(db.query(models.NewsArticle.status, func.count(models.NewsArticle.id))
                          .group_by(models.NewsArticle.status).all()),
        "deleted_total": db.query(models.NewsArticle)
                           .filter(models.NewsArticle.is_deleted.is_(True)).count(),
    }
    facets["by_status"] = {(k.value if hasattr(k, "value") else str(k)): v
                           for k, v in facets["by_status"].items()}

    return {"total": total, "page": payload.page, "page_size": payload.page_size,
            "items": items, "facets": facets}


# ---------------------------------------------------------------------------
# 刪除舊新聞（軟刪除 + 註記）
# ---------------------------------------------------------------------------
class SoftDeleteIn(BaseModel):
    article_ids: Optional[list[str]] = None
    older_than_days: Optional[int] = Field(default=None, ge=1, le=3650)
    source_slugs: Optional[list[str]] = None
    status: Optional[Literal["active", "archived"]] = None
    exclude_bookmarked: bool = True
    note: str = Field(..., min_length=1, max_length=2000)
    dry_run: bool = False


@router.post("/articles/soft-delete", summary="（後台）刪除舊新聞並留下註記")
def soft_delete(payload: SoftDeleteIn,
                current_user: models.User = Depends(require_admin),
                db: Session = Depends(get_db)):
    if not payload.article_ids and payload.older_than_days is None:
        raise HTTPException(status_code=400, detail="請提供 article_ids 或 older_than_days")

    query = db.query(models.NewsArticle).filter(models.NewsArticle.is_deleted.is_(False))
    if payload.article_ids:
        query = query.filter(models.NewsArticle.id.in_(payload.article_ids))
    if payload.older_than_days is not None:
        cutoff = datetime.utcnow() - timedelta(days=payload.older_than_days)
        query = query.filter(models.NewsArticle.collected_at < cutoff)
    if payload.source_slugs:
        sub = db.query(models.NewsSource.id).filter(
            models.NewsSource.slug.in_(payload.source_slugs))
        query = query.filter(models.NewsArticle.source_id.in_(sub))
    if payload.status:
        query = query.filter(models.NewsArticle.status == payload.status)

    matched = query.count()

    blocked = 0
    if payload.exclude_bookmarked:
        bookmarked = db.query(models.UserNewsBookmark.article_id)
        blocked = query.filter(models.NewsArticle.id.in_(bookmarked)).count()
        query = query.filter(~models.NewsArticle.id.in_(bookmarked))

    will_affect = matched - blocked

    if payload.dry_run:
        return {"action": "soft_delete", "dry_run": True,
                "affected_count": will_affect, "blocked_bookmarked": blocked,
                "note": payload.note,
                "message": f"預計軟刪除 {will_affect} 筆；因已被使用者保留而保護 {blocked} 筆。"}

    now = datetime.utcnow()
    affected = query.update({
        models.NewsArticle.is_deleted: True,
        models.NewsArticle.status: models.NewsArticleStatus.deleted,
        models.NewsArticle.deleted_at: now,
        models.NewsArticle.deleted_by: current_user.id,
        models.NewsArticle.delete_note: payload.note,
    }, synchronize_session=False)
    db.commit()

    write_audit_log(db, current_user, "news_soft_delete", target_type="news_article",
                    target_id=(payload.article_ids[0] if payload.article_ids
                               and len(payload.article_ids) == 1 else None),
                    detail=dumps({"affected": affected, "blocked_bookmarked": blocked,
                                  "older_than_days": payload.older_than_days,
                                  "source_slugs": payload.source_slugs,
                                  "note": payload.note}))

    return {"action": "soft_delete", "dry_run": False,
            "affected_count": affected, "blocked_bookmarked": blocked, "note": payload.note,
            "message": f"已軟刪除 {affected} 筆（保護 {blocked} 筆已被保留的新聞）。"
                       "已刪除項目仍可於後台查詢與還原。"}


class RestoreIn(BaseModel):
    article_ids: list[str] = Field(..., min_length=1)
    note: Optional[str] = Field(default=None, max_length=2000)


@router.post("/articles/restore", summary="（後台）還原已刪除的新聞")
def restore(payload: RestoreIn,
            current_user: models.User = Depends(require_admin),
            db: Session = Depends(get_db)):
    affected = (db.query(models.NewsArticle)
                .filter(models.NewsArticle.id.in_(payload.article_ids),
                        models.NewsArticle.is_deleted.is_(True))
                .update({
                    models.NewsArticle.is_deleted: False,
                    models.NewsArticle.status: models.NewsArticleStatus.archived,
                    models.NewsArticle.deleted_at: None,
                    models.NewsArticle.deleted_by: None,
                    models.NewsArticle.delete_note: None,
                }, synchronize_session=False))
    db.commit()

    write_audit_log(db, current_user, "news_restore", target_type="news_article",
                    detail=dumps({"affected": affected, "ids": payload.article_ids[:50],
                                  "note": payload.note}))
    return {"action": "restore", "affected_count": affected,
            "message": f"已還原 {affected} 筆（狀態設為 archived）。"}


class PinIn(BaseModel):
    digest_date: str
    article_id: str
    is_pinned: bool = True


@router.post("/digest/pin", summary="（後台）置頂／取消置頂每日精選項目")
def pin_digest(payload: PinIn,
               current_user: models.User = Depends(require_admin),
               db: Session = Depends(get_db)):
    row = (db.query(models.NewsDailyDigest)
           .filter(models.NewsDailyDigest.digest_date == payload.digest_date,
                   models.NewsDailyDigest.article_id == payload.article_id).first())
    if not row:
        raise HTTPException(status_code=404, detail="該日精選中沒有這則新聞")
    row.is_pinned = payload.is_pinned
    db.commit()
    write_audit_log(db, current_user, "news_pin" if payload.is_pinned else "news_unpin",
                    target_type="news_digest", target_id=payload.article_id,
                    detail=dumps({"digest_date": payload.digest_date}))
    return {"ok": True, "digest_date": payload.digest_date,
            "article_id": payload.article_id, "is_pinned": payload.is_pinned}


# ---------------------------------------------------------------------------
# 來源健康度
# ---------------------------------------------------------------------------
@router.get("/sources", summary="（後台）來源健康度")
def admin_sources(current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    sync_sources(db)
    db.commit()
    counts = dict(db.query(models.NewsArticle.source_id, func.count(models.NewsArticle.id))
                  .filter(models.NewsArticle.is_deleted.is_(False))
                  .group_by(models.NewsArticle.source_id).all())
    rows = db.query(models.NewsSource).order_by(models.NewsSource.slug).all()
    return [{
        "id": s.id, "slug": s.slug, "name_zh": s.name_zh, "name_en": s.name_en,
        "homepage": s.homepage,
        "kind": s.kind.value if s.kind else None,
        "evidence_level": s.evidence_level.value if s.evidence_level else None,
        "weight": float(s.weight or 0), "lang": s.lang,
        "is_enabled": bool(s.is_enabled),
        "is_custom": bool(getattr(s, "is_custom", False)),
        "notes": s.notes,
        "config": _redact_config(loads(s.config, {})),
        "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
        "last_error": s.last_error,
        "consecutive_failures": s.consecutive_failures,
        "article_count": counts.get(s.id, 0),
    } for s in rows]


class SourceUpdateIn(BaseModel):
    slug: str
    is_enabled: Optional[bool] = None
    weight: Optional[float] = Field(default=None, ge=0, le=1)
    config: Optional[dict[str, Any]] = None
    notes: Optional[str] = None
    reset_failures: bool = False


@router.put("/sources", summary="（後台）更新來源設定（爬蟲選擇器等，不需重新部署）")
def update_source(payload: SourceUpdateIn,
                  current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    row = db.query(models.NewsSource).filter(models.NewsSource.slug == payload.slug).first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到這個來源")
    if payload.is_enabled is not None:
        row.is_enabled = payload.is_enabled
    if payload.weight is not None:
        row.weight = f"{payload.weight:.2f}"
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.config is not None:
        merged = loads(row.config, {})
        merged.update(payload.config)
        row.config = dumps(merged)
    if payload.reset_failures:
        row.consecutive_failures = 0
        row.last_error = None
    db.commit()
    audit_detail = payload.model_dump(exclude_none=True)
    if "config" in audit_detail:
        audit_detail["config"] = _redact_config(audit_detail["config"])
    write_audit_log(db, current_user, "news_update_source", target_type="news_source",
                    target_id=row.id, detail=dumps(audit_detail))
    return {"ok": True, "slug": row.slug}


# ---------------------------------------------------------------------------
# 收集執行紀錄 / 手動觸發
# ---------------------------------------------------------------------------
@router.get("/runs", summary="（後台）收集執行紀錄")
def list_runs(limit: int = Query(30, ge=1, le=200),
              current_user: models.User = Depends(require_admin),
              db: Session = Depends(get_db)):
    rows = (db.query(models.NewsCollectionRun)
            .order_by(models.NewsCollectionRun.started_at.desc()).limit(limit).all())
    return [{
        "id": r.id, "run_date": r.run_date, "trigger_type": r.trigger_type,
        "status": r.status.value if r.status else None,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_ms": r.duration_ms,
        "fetched_count": r.fetched_count, "new_count": r.new_count,
        "duplicate_count": r.duplicate_count, "filtered_count": r.filtered_count,
        "digest_count": r.digest_count, "linked_entity_count": r.linked_entity_count,
        "per_source": loads(r.per_source, {}),
        "error_message": r.error_message,
    } for r in rows]


class CollectIn(BaseModel):
    target_date: Optional[str] = None


@router.post("/collect", summary="（後台）立即執行一次收集")
def collect_now(payload: CollectIn,
                current_user: models.User = Depends(require_admin),
                db: Session = Depends(get_db)):
    write_audit_log(db, current_user, "news_manual_collect", target_type="news_run",
                    detail=dumps({"target_date": payload.target_date}))
    return run_daily_collection(db, target_date=payload.target_date,
                                trigger_type="manual", triggered_by=current_user.id)


@router.post("/collect/scheduled", summary="（排程專用）以共享密鑰觸發收集，不需登入")
def collect_scheduled(payload: CollectIn,
                      authorization: Optional[str] = Header(default=None),
                      db: Session = Depends(get_db)):
    """給每日 04:00 的外部排程呼叫（Claude 排程任務 / GitHub Actions / Cron Worker）。

    Render free plan 沒有內建 Cron Job，因此改由外部排程打這個端點。

    密鑰用 `Authorization: Bearer <NEWS_COLLECT_SECRET>` 標頭傳送，**不要放在網址查詢字串**——
    查詢字串會被 Render 的存取日誌、反向代理與瀏覽器歷史記錄下來，標頭不會。

    密鑰以環境變數 NEWS_COLLECT_SECRET 設定；未設定時一律拒絕（避免部署時忘了設就變成公開端點）。
    """
    expected = os.environ.get("NEWS_COLLECT_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="尚未設定 NEWS_COLLECT_SECRET，排程端點停用中")

    token = (authorization or "").removeprefix("Bearer ").removeprefix("bearer ").strip()
    # 用 compare_digest 避免以時間差推測密鑰
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="密鑰不正確")

    return run_daily_collection(db, target_date=payload.target_date,
                                trigger_type="scheduled")


# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
@router.get("/settings", summary="（後台）新聞模組設定")
def read_settings(current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    return get_settings(db)


class SettingsIn(BaseModel):
    daily_digest_size: Optional[int] = Field(default=None, ge=1, le=50)
    min_relevance_score: Optional[float] = Field(default=None, ge=0, le=1)
    lookback_days: Optional[int] = Field(default=None, ge=1, le=30)
    max_per_source_per_day: Optional[int] = Field(default=None, ge=1, le=50)
    auto_archive_days: Optional[int] = Field(default=None, ge=7, le=3650)
    link_ingredients: Optional[bool] = None
    disclaimer_zh: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    summary_enabled: Optional[bool] = None
    # 上下限與 short_summary 模組一致：太短寫不出證據層級，太長就失去「快速掃讀」的意義
    summary_length: Optional[int] = Field(default=None,
                                          ge=short_summary.MIN_CHAR_LIMIT,
                                          le=short_summary.MAX_CHAR_LIMIT)


@router.put("/settings", summary="（後台）更新新聞模組設定")
def update_settings(payload: SettingsIn,
                    current_user: models.User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    changed = payload.model_dump(exclude_none=True)
    if not changed:
        raise HTTPException(status_code=400, detail="沒有要更新的設定")
    for key, value in changed.items():
        set_setting(db, key, value, updated_by=current_user.id)
    db.commit()
    write_audit_log(db, current_user, "news_update_settings", target_type="news_setting",
                    detail=dumps(changed))
    return {"ok": True, "updated": changed}


class BackfillIn(BaseModel):
    lang: str = Field(description="摘要語系：zh-TW / en / ko")
    days: int = Field(default=30, ge=1, le=365, description="回補幾天內收集的文章")
    limit: int = Field(default=30, ge=1, le=100, description="這一批最多處理幾篇")
    include_stale: bool = Field(
        default=False,
        description="連「字數上限已經改過、內容還是舊長度」的摘要也一起重產")


@router.post("/summaries/backfill", summary="（後台）回補指定語系的簡短摘要")
def backfill_summary(payload: BackfillIn,
                     current_user: models.User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    """把還沒有該語系摘要的舊文章補上。

    刻意做成「按一次補一批、回傳還剩幾篇」而不是一次全補完：
    回補會實際打 AI API，一次上千篇既會讓請求逾時，費用也不受管理者控制。
    """
    try:
        result = backfill_summaries(db, payload.lang, days=payload.days,
                                    limit=payload.limit,
                                    include_stale=payload.include_stale)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    write_audit_log(db, current_user, "news_backfill_summary", target_type="news_summary",
                    detail=dumps({"lang": payload.lang, "days": payload.days,
                                  "limit": payload.limit,
                                  "include_stale": payload.include_stale,
                                  "written": result["written"]}))
    db.commit()
    return result


@router.get("/summaries/stats", summary="（後台）各語系摘要覆蓋率")
def summary_stats(current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """讓管理者知道「哪個語系補到什麼程度」，才有辦法決定要不要再按一次回補。"""
    total = (db.query(models.NewsArticle)
             .filter(models.NewsArticle.is_deleted.is_(False)).count())
    cfg = get_settings(db)
    char_limit = int(cfg.get("summary_length", short_summary.DEFAULT_CHAR_LIMIT))

    out = []
    for lang in short_summary.SUMMARY_LANGS:
        rows = db.query(models.NewsArticleSummary).filter(
            models.NewsArticleSummary.lang == lang)
        have = rows.count()
        # 「字數上限改過」與「降級產生的」都算需要重產，分開統計讓管理者知道原因
        outdated = rows.filter(models.NewsArticleSummary.char_limit != char_limit).count()
        degraded = rows.filter(models.NewsArticleSummary.is_ai.is_(False)).count()
        ai = rows.filter(models.NewsArticleSummary.is_ai.is_(True)).count()
        needs_regen = rows.filter(
            (models.NewsArticleSummary.char_limit != char_limit)
            | (models.NewsArticleSummary.is_ai.is_(False))).count()
        out.append({"lang": lang, "have": have, "missing": max(0, total - have),
                    "stale": needs_regen, "outdated_length": outdated,
                    "degraded": degraded, "ai_generated": ai})
    return {"total_articles": total, "char_limit": char_limit,
            "summary_enabled": bool(cfg.get("summary_enabled", True)),
            "has_api_key": bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip()),
            "by_lang": out}


@router.get("/summaries/test-key", summary="（後台）實際打一次 API，檢測 ANTHROPIC_API_KEY 是否可用")
def test_summary_api_key(current_user: models.User = Depends(require_admin),
                         db: Session = Depends(get_db)):
    """只檢查環境變數存不存在是不夠的——金鑰打錯／過期／額度用盡時變數一樣在，
    但每次生成都會失敗然後靜靜退回降級，症狀跟「沒設」完全一樣。
    這支會實際送一個 max_tokens=1 的最小請求，把對方真正的回應講清楚。

    回應不包含金鑰本身，只有狀態與截短後的錯誤訊息。
    """
    result = short_summary.check_api_key()
    write_audit_log(db, current_user, "news_test_api_key", target_type="news_setting",
                    detail=dumps({"ok": result["ok"], "reason": result["reason"]}))
    db.commit()
    return result


# ===========================================================================
# 自訂新聞來源（管理者只輸入網址，其餘由系統推斷）
# ===========================================================================
def _slugify_url(url: str) -> str:
    """由網址產生 slug。加 custom- 前綴是為了一眼分辨自訂來源，
    也避免跟 sources.py 裡的官方 slug（who/nci/pubmed…）撞名。"""
    parsed = urlparse(discover.normalize_url(url))
    raw = f"{parsed.netloc}{parsed.path}".lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")[:48]
    return f"custom-{slug or 'source'}"


class SourceProbeIn(BaseModel):
    url: str = Field(min_length=4, max_length=500)


@router.post("/sources/probe", summary="（後台）試抓一個網址，回報能不能當新聞來源")
def probe_source(payload: SourceProbeIn,
                 current_user: models.User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    """只試抓、不儲存。管理者可以先看結果再決定要不要加。"""
    return asyncio.run(discover.probe(
        payload.url,
        contact_email=os.environ.get("NEWS_CONTACT_EMAIL", "research@example.org")))


class SourceCreateIn(BaseModel):
    url: str = Field(min_length=4, max_length=500)
    name: Optional[str] = Field(default=None, max_length=80)
    # 預設一律是「一般新聞」最低權重，避免商業新聞在排序上蓋過人體試驗研究。
    # 確定是政府／學術單位的站才勾這個，會提升到國家衛生政策層級與中等權重。
    is_official: bool = False
    note: Optional[str] = Field(default=None, max_length=500)


@router.post("/sources", summary="（後台）新增自訂新聞來源（只需網址）")
def create_source(payload: SourceCreateIn,
                  current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """新增前一定會實際抓一次，抓不到就不讓存。

    這是刻意的：允許存一個抓不到東西的來源，問題會延到隔天清晨 4:00 的排程才爆，
    那時沒有人在看，而且錯誤會混在其他來源的統計裡很難發現。
    寧可現在就擋下來並說明原因。
    """
    probe = asyncio.run(discover.probe(
        payload.url,
        contact_email=os.environ.get("NEWS_CONTACT_EMAIL", "research@example.org")))
    if not probe["ok"]:
        raise HTTPException(status_code=400, detail={
            "message": probe.get("error") or "這個網址抓不到任何文章，未新增。",
            "warnings": probe.get("warnings", []),
            "probe": probe,
        })

    slug = _slugify_url(payload.url)
    if db.query(models.NewsSource).filter(models.NewsSource.slug == slug).first():
        raise HTTPException(status_code=409, detail=f"這個網址已經加過了（{slug}）。")

    name = (payload.name or probe["name"] or urlparse(probe["url"]).netloc)[:80]
    level = (models.NewsEvidenceLevel.national_policy if payload.is_official
             else models.NewsEvidenceLevel.general_news)
    row = models.NewsSource(
        slug=slug, name_zh=name, name_en=name, homepage=probe["homepage"],
        kind=models.NewsCollectorKind(probe["kind"]),
        evidence_level=level,
        weight="0.55" if payload.is_official else "0.30",
        lang=probe["lang"], prefiltered=False, is_enabled=True, is_custom=True,
        config=dumps(probe["config"]),
        notes=payload.note or "；".join(probe.get("warnings", [])) or None,
    )
    db.add(row)
    write_audit_log(db, current_user, "news_create_source", target_type="news_source",
                    target_id=slug,
                    detail=dumps({"url": payload.url, "kind": probe["kind"],
                                  "found": probe["found"], "is_official": payload.is_official}))
    db.commit()
    return {"ok": True, "slug": slug, "name": name, "kind": probe["kind"],
            "found": probe["found"], "samples": probe["samples"],
            "warnings": probe.get("warnings", [])}


@router.delete("/sources/{slug}", summary="（後台）刪除自訂新聞來源")
def delete_source(slug: str,
                  current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """只能刪自訂來源，而且必須沒有留下任何文章。

    官方來源不給刪：它們定義在 sources.py，刪掉之後下次部署 sync_sources()
    又會建回來，變成「刪了又出現」的鬼打牆。要停用請用啟用開關。

    已經收過文章的來源也不給刪：文章有外鍵指向來源，硬刪會讓那些新聞
    失去出處。同樣請改用停用。
    """
    row = db.query(models.NewsSource).filter(models.NewsSource.slug == slug).first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到這個來源。")
    if not row.is_custom:
        raise HTTPException(status_code=400,
                            detail="這是系統內建來源，不能刪除。請改用啟用／停用開關。")
    count = (db.query(models.NewsArticle)
             .filter(models.NewsArticle.source_id == row.id).count())
    if count:
        raise HTTPException(status_code=409, detail=(
            f"這個來源底下還有 {count} 篇新聞，刪掉會讓那些新聞失去出處。"
            "請改用停用，或先把那些新聞刪除。"))
    db.delete(row)
    write_audit_log(db, current_user, "news_delete_source", target_type="news_source",
                    target_id=slug, detail=dumps({"name": row.name_zh}))
    db.commit()
    return {"ok": True, "deleted": slug}


# ===========================================================================
# 主題過濾關鍵字 CRUD
# ===========================================================================
@router.get("/keywords", summary="（後台）主題過濾關鍵字清單")
def list_keywords(current_user: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    news_keywords.seed_defaults(db)
    rows = (db.query(models.NewsKeyword)
            .order_by(models.NewsKeyword.group, models.NewsKeyword.term).all())
    grouped: dict[str, list] = {g: [] for g in news_keywords.GROUPS}
    for r in rows:
        grouped.setdefault(r.group, []).append({
            "id": r.id, "term": r.term, "is_enabled": bool(r.is_enabled),
            "is_default": bool(r.is_default), "note": r.note,
        })
    return {"groups": news_keywords.GROUPS,
            "labels": news_keywords.GROUP_LABEL,
            "counts": news_keywords.counts(db),
            "items": grouped,
            "explain": ("一篇文章必須同時命中『中藥／天然物』與『腫瘤／癌症』兩組，"
                        "才會被收進來（來源本身已鎖定主題者除外）。"
                        "因此兩組都不能全部停用。")}


class KeywordIn(BaseModel):
    group: Literal["tcm", "cancer"]
    term: str = Field(min_length=1, max_length=80)
    note: Optional[str] = Field(default=None, max_length=200)


@router.post("/keywords", summary="（後台）新增關鍵字")
def create_keyword(payload: KeywordIn,
                   current_user: models.User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    term = news_keywords.normalize(payload.term)
    if not term:
        raise HTTPException(status_code=422, detail="關鍵字不能是空白。")
    exists = (db.query(models.NewsKeyword)
              .filter(models.NewsKeyword.group == payload.group,
                      models.NewsKeyword.term == term).first())
    if exists:
        raise HTTPException(status_code=409, detail=f"「{term}」已經在這一組裡了。")
    row = models.NewsKeyword(group=payload.group, term=term, note=payload.note,
                             is_default=False, is_enabled=True,
                             created_by=current_user.id)
    db.add(row)
    write_audit_log(db, current_user, "news_create_keyword", target_type="news_keyword",
                    detail=dumps({"group": payload.group, "term": term}))
    db.commit()
    return {"ok": True, "id": row.id, "term": term}


class KeywordUpdateIn(BaseModel):
    term: Optional[str] = Field(default=None, min_length=1, max_length=80)
    is_enabled: Optional[bool] = None
    note: Optional[str] = Field(default=None, max_length=200)


def _guard_last_enabled(db: Session, group: str, exclude_id: str) -> None:
    """擋下「把某一組的最後一個啟用關鍵字停用/刪除」。

    兩組任一為空時，relevance() 會判定所有文章都不相關，
    當天收集會全軍覆沒而且完全沒有錯誤訊息——那是最難查的一種壞法。
    """
    remaining = (db.query(models.NewsKeyword)
                 .filter(models.NewsKeyword.group == group,
                         models.NewsKeyword.is_enabled.is_(True),
                         models.NewsKeyword.id != exclude_id).count())
    if remaining == 0:
        raise HTTPException(status_code=400, detail=(
            f"「{news_keywords.GROUP_LABEL.get(group, group)}」至少要保留一個啟用中的關鍵字。"
            "這一組全空的話，之後收集會判定所有文章都不相關，而且不會有任何錯誤訊息。"))


@router.put("/keywords/{keyword_id}", summary="（後台）修改關鍵字")
def update_keyword(keyword_id: str, payload: KeywordUpdateIn,
                   current_user: models.User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    row = db.query(models.NewsKeyword).filter(models.NewsKeyword.id == keyword_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到這個關鍵字。")
    changed = payload.model_dump(exclude_none=True)
    if not changed:
        raise HTTPException(status_code=400, detail="沒有要更新的內容。")

    if changed.get("is_enabled") is False:
        _guard_last_enabled(db, row.group, row.id)
    if "term" in changed:
        term = news_keywords.normalize(changed["term"])
        if not term:
            raise HTTPException(status_code=422, detail="關鍵字不能是空白。")
        dup = (db.query(models.NewsKeyword)
               .filter(models.NewsKeyword.group == row.group,
                       models.NewsKeyword.term == term,
                       models.NewsKeyword.id != row.id).first())
        if dup:
            raise HTTPException(status_code=409, detail=f"「{term}」已經在這一組裡了。")
        row.term = term
    if "is_enabled" in changed:
        row.is_enabled = bool(changed["is_enabled"])
    if "note" in changed:
        row.note = changed["note"]

    write_audit_log(db, current_user, "news_update_keyword", target_type="news_keyword",
                    target_id=row.id, detail=dumps(changed))
    db.commit()
    return {"ok": True, "id": row.id, "term": row.term, "is_enabled": row.is_enabled}


@router.delete("/keywords/{keyword_id}", summary="（後台）刪除關鍵字")
def delete_keyword(keyword_id: str,
                   current_user: models.User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    row = db.query(models.NewsKeyword).filter(models.NewsKeyword.id == keyword_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到這個關鍵字。")
    if row.is_enabled:
        _guard_last_enabled(db, row.group, row.id)
    group, term = row.group, row.term
    db.delete(row)
    write_audit_log(db, current_user, "news_delete_keyword", target_type="news_keyword",
                    detail=dumps({"group": group, "term": term}))
    db.commit()
    return {"ok": True, "deleted": term}
