"""每日收集流程：抓取 → 主題過濾 → 去重 → 分類評分 → AI 摘要 → 實體連結
→ 每日 Top N → 自動封存。

同步版本（配合平台既有的 SQLAlchemy Session 慣例）。
收集器本身是 async，這裡以 asyncio.run() 包起來；FastAPI 的同步路由會在
threadpool 執行，因此不會卡住事件迴圈。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import models

from .collectors import collect_all, hamming, simhash64
from .collectors.base import RawItem
from .entity_linker import EntityIndex, article_text, build_index
from .scoring import classify, rank_score, relevance, select_daily
from .sources import SOURCES, SOURCE_BY_SLUG
from . import short_summary
from .summarizer import summarize

logger = logging.getLogger(__name__)

TAIPEI = timezone(timedelta(hours=8))   # 台灣全年 UTC+8，無日光節約
# 漢明距離 ≤12 視為近似重複。實測：僅差一字的中英標題 4–9，主題不同 25–37。
SIMHASH_THRESHOLD = 12

DEFAULT_SETTINGS = {
    "daily_digest_size": 10,
    "min_relevance_score": 0.35,
    "lookback_days": 3,
    "max_per_source_per_day": 4,
    "auto_archive_days": 90,
    "link_ingredients": True,
    # 簡短摘要（news_article_summaries）：預設 200 字，管理者可在後台調整。
    "summary_enabled": True,
    "summary_length": short_summary.DEFAULT_CHAR_LIMIT,
    "disclaimer_zh": (
        "本區內容為研究情報彙整，僅供科研查證與安全監測參考，不構成醫療診斷或治療建議。"
        "任何中藥使用須由合格醫療專業人員評估肝腎功能、凝血狀態及現行化療／標靶／免疫治療之交互作用。"
    ),
}


# ---------------------------------------------------------------------------
# JSON 欄位輔助（本模組的陣列型資料以 JSON 字串存在 Text 欄位）
# ---------------------------------------------------------------------------
def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value, default=None):
    if not value:
        return default if default is not None else []
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default if default is not None else []


def taipei_today() -> str:
    return datetime.now(TAIPEI).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 設定與來源
# ---------------------------------------------------------------------------
def get_settings(db: Session) -> dict:
    cfg = dict(DEFAULT_SETTINGS)
    for row in db.query(models.NewsSetting).all():
        cfg[row.key] = loads(row.value, DEFAULT_SETTINGS.get(row.key))
    return cfg


def set_setting(db: Session, key: str, value, updated_by: str | None = None) -> None:
    row = db.query(models.NewsSetting).filter(models.NewsSetting.key == key).first()
    if row is None:
        row = models.NewsSetting(key=key, description=None)
        db.add(row)
    row.value = dumps(value)
    row.updated_by = updated_by
    row.updated_at = datetime.utcnow()


def sync_sources(db: Session) -> dict[str, str]:
    """把 sources.py 的定義同步進資料庫（冪等）。回傳 slug -> source_id。

    保留管理者在後台改過的 config（例如爬蟲選擇器修正、api_key）。
    """
    existing = {s.slug: s for s in db.query(models.NewsSource).all()}
    for sd in SOURCES:
        row = existing.get(sd.slug)
        if row is None:
            row = models.NewsSource(slug=sd.slug)
            db.add(row)
        row.name_zh = sd.name_zh
        row.name_en = sd.name_en
        row.homepage = sd.homepage
        row.kind = models.NewsCollectorKind(sd.kind.value)
        row.evidence_level = models.NewsEvidenceLevel(sd.evidence_level.value)
        row.weight = f"{sd.weight:.2f}"
        row.lang = sd.lang
        row.prefiltered = sd.prefiltered
        row.notes = sd.notes
        merged = dict(sd.config)
        merged.update(loads(row.config, {}) or {})
        row.config = dumps(merged)
    db.flush()
    return {s.slug: s.id for s in db.query(models.NewsSource).all()}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run_daily_collection(
    db: Session,
    *,
    target_date: str | None = None,
    trigger_type: str = "scheduled",
    triggered_by: str | None = None,
    contact_email: str | None = None,
    anthropic_api_key: str | None = None,
    pubmed_api_key: str | None = None,
) -> dict:
    import os

    started = datetime.utcnow()
    run_date = target_date or taipei_today()
    settings = get_settings(db)
    slug_to_id = sync_sources(db)

    run = models.NewsCollectionRun(
        run_date=run_date, trigger_type=trigger_type, triggered_by=triggered_by,
        status=models.NewsRunStatus.running,
    )
    db.add(run)
    db.flush()

    # ---- 1) 抓取（非同步收集器，用 asyncio.run 包起來）----
    enabled = {s.slug for s in db.query(models.NewsSource)
               .filter(models.NewsSource.is_enabled.is_(True)).all()}
    active_sources = [s for s in SOURCES if s.slug in enabled] or SOURCES

    items, stats = asyncio.run(collect_all(
        contact_email=contact_email or os.environ.get("NEWS_CONTACT_EMAIL", "research@example.org"),
        sources=active_sources,
        lookback_days=settings["lookback_days"],
        pubmed_api_key=pubmed_api_key or os.environ.get("PUBMED_API_KEY"),
    ))
    _update_source_health(db, slug_to_id, stats)

    # ---- 2) 主題過濾 ----
    candidates: list[tuple[RawItem, dict, float]] = []
    filtered = 0
    for it in items:
        rel = relevance(it)
        if rel < settings["min_relevance_score"]:
            filtered += 1
            continue
        candidates.append((it, classify(it), rel))

    # ---- 3) 去重 ----
    fresh, dup_count = _dedupe(db, candidates)

    # ---- 4) AI 摘要 ----
    summaries = summarize([(it, meta) for it, meta, _ in fresh],
                          api_key=anthropic_api_key)

    # ---- 5) 寫入文章 ----
    entity_index: EntityIndex | None = None
    linked_total = 0
    persisted: list[dict] = []

    for (item, meta, rel), summ in zip(fresh, summaries):
        score = rank_score(item, meta, rel)
        src = SOURCE_BY_SLUG[item.source_slug]
        article = models.NewsArticle(
            source_id=slug_to_id[item.source_slug],
            url=item.url,
            url_hash=item.url_hash,
            content_hash=item.content_hash,
            title_simhash=f"{simhash64(item.title) & 0xFFFFFFFFFFFFFFFF:016x}",
            external_id=item.external_id,
            doi=item.doi,
            title=item.title,
            title_zh=summ.get("title_zh"),
            abstract=item.abstract,
            summary_zh=summ.get("summary_zh"),
            key_points=dumps(summ.get("key_points") or []),
            caveat_zh=summ.get("caveat_zh"),
            authors=item.authors,
            journal=item.journal,
            lang=item.lang,
            evidence_level=models.NewsEvidenceLevel(src.evidence_level.value),
            evidence_maturity=models.NewsEvidenceMaturity(meta["evidence_maturity"]),
            study_design=item.study_design,
            cancer_types=dumps(meta["cancer_types"]),
            intervention_types=dumps(meta["intervention_types"]),
            tags=dumps(meta["tags"]),
            is_safety_signal=meta["is_safety_signal"],
            relevance_score=f"{rel:.4f}",
            rank_score=f"{score:.4f}",
            published_at=item.published_at.replace(tzinfo=None) if item.published_at else None,
            source_updated_at=(item.source_updated_at.replace(tzinfo=None)
                               if item.source_updated_at else None),
            raw_payload=dumps(item.raw or {}),
            search_blob=_search_blob(item, summ),
        )
        db.add(article)
        db.flush()   # 取得 id 才能寫實體關聯

        # ---- 實體連結（藥材 / 成分 / 靶點 / 疾病）----
        if entity_index is None:
            entity_index = build_index(db, include_ingredients=settings["link_ingredients"])
        linked_count, entity_names = _link_entities(db, article, entity_index, summ)
        linked_total += linked_count
        # 把比對到的實體中文名併進搜尋欄位：這樣後台搜「胃癌」也找得到
        # 標題是英文的那篇 gastric cancer 研究（沒有 AI 翻譯時尤其重要）。
        if entity_names:
            article.search_blob = (article.search_blob + " "
                                   + " ".join(entity_names).lower())[:8000]

        persisted.append({
            "article": article,
            "source_slug": item.source_slug,
            "rank_score": score,
            "is_safety_signal": meta["is_safety_signal"],
            "evidence_maturity": meta["evidence_maturity"],
        })

    # ---- 6) 每日 Top N ----
    fresh_ids = {p["article"].id for p in persisted}
    pool = persisted + _recent_unpicked(db, settings["lookback_days"], fresh_ids)
    picked = select_daily(pool, size=settings["daily_digest_size"],
                          max_per_source=settings["max_per_source_per_day"])

    db.query(models.NewsDailyDigest).filter(
        models.NewsDailyDigest.digest_date == run_date,
        models.NewsDailyDigest.is_pinned.is_(False),
    ).delete(synchronize_session=False)

    for p in picked:
        db.add(models.NewsDailyDigest(
            digest_date=run_date,
            article_id=p["article"].id,
            rank=p["rank"],
            rank_score=f"{p['rank_score']:.4f}",
            pick_reason=_pick_reason(p),
        ))

    # ---- 7) 自動封存（超過天數且無人保留）----
    archived = _auto_archive(db, settings["auto_archive_days"])

    # ---- 8) 收尾 ----
    finished = datetime.utcnow()
    errors = {k: v["error"] for k, v in stats.items() if v.get("error")}
    if errors and len(errors) == len(stats):
        status = models.NewsRunStatus.failed
    elif errors:
        status = models.NewsRunStatus.partial
    else:
        status = models.NewsRunStatus.success

    run.status = status
    run.finished_at = finished
    run.duration_ms = int((finished - started).total_seconds() * 1000)
    run.fetched_count = len(items)
    run.new_count = len(persisted)
    run.duplicate_count = dup_count
    run.filtered_count = filtered
    run.digest_count = len(picked)
    run.linked_entity_count = linked_total
    run.per_source = dumps(stats)
    run.error_message = "; ".join(f"{k}: {v}" for k, v in errors.items()) or None

    db.commit()

    return {
        "run_id": run.id,
        "run_date": run_date,
        "status": status.value,
        "fetched": len(items),
        "filtered_out": filtered,
        "duplicates": dup_count,
        "new_articles": len(persisted),
        "digest_size": len(picked),
        "linked_entities": linked_total,
        "archived": archived,
        "duration_ms": run.duration_ms,
        "per_source": stats,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# 輔助
# ---------------------------------------------------------------------------
def _search_blob(item: RawItem, summ: dict) -> str:
    parts = [item.title, summ.get("title_zh"), summ.get("summary_zh"),
             (item.abstract or "")[:2000], item.external_id, item.doi]
    return " ".join(p for p in parts if p).lower()[:8000]


def _link_entities(db: Session, article: models.NewsArticle,
                   index: EntityIndex, summ: dict) -> tuple[int, list[str]]:
    """回傳 (連結數, 實體顯示名稱清單)。名稱會被併進 search_blob 供後台搜尋。"""
    text = article_text(article.title, summ.get("title_zh"),
                        article.abstract, summ.get("summary_zh"))
    count = 0
    names: list[str] = []
    for hit in index.find(text):
        ref = hit.ref
        if ref.display_name:
            names.append(ref.display_name)
        db.add(models.NewsArticleEntity(
            article_id=article.id,
            entity_type=models.NewsEntityType(ref.entity_type),
            entity_key=ref.entity_key,
            herb_id=ref.herb_id,
            mol_id=ref.mol_id,
            tar_id=ref.tar_id,
            dis_id=ref.dis_id,
            display_name=ref.display_name,
            matched_text=hit.matched_text,
            match_type=ref.match_type,
        ))
        count += 1
    return count, names


def _dedupe(db: Session, candidates: list[tuple[RawItem, dict, float]]):
    """三層去重：URL hash → 內容 hash → 標題 simhash 近似。"""
    if not candidates:
        return [], 0

    url_hashes = [c[0].url_hash for c in candidates]
    content_hashes = [c[0].content_hash for c in candidates]

    known_urls = {r[0] for r in db.query(models.NewsArticle.url_hash)
                  .filter(models.NewsArticle.url_hash.in_(url_hashes)).all()}
    known_content = {r[0] for r in db.query(models.NewsArticle.content_hash)
                     .filter(models.NewsArticle.content_hash.in_(content_hashes)).all() if r[0]}

    cutoff = datetime.utcnow() - timedelta(days=14)
    recent_simhashes = [r[0] for r in db.query(models.NewsArticle.title_simhash)
                        .filter(models.NewsArticle.collected_at >= cutoff,
                                models.NewsArticle.title_simhash.isnot(None)).all() if r[0]]

    kept, dup = [], 0
    seen_url, seen_content, batch_sim = set(), set(), []

    # 高分優先保留，重複時留下權威度較高的版本
    for item, meta, rel in sorted(candidates, key=lambda c: -c[2]):
        if item.url_hash in known_urls or item.url_hash in seen_url:
            dup += 1
            continue
        if item.content_hash in known_content or item.content_hash in seen_content:
            dup += 1
            continue
        sh = f"{simhash64(item.title) & 0xFFFFFFFFFFFFFFFF:016x}"
        if any(_hamming_hex(sh, other) <= SIMHASH_THRESHOLD
               for other in recent_simhashes + batch_sim):
            dup += 1
            continue
        kept.append((item, meta, rel))
        seen_url.add(item.url_hash)
        seen_content.add(item.content_hash)
        batch_sim.append(sh)

    return kept, dup


def _hamming_hex(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except (TypeError, ValueError):
        return 64


def _recent_unpicked(db: Session, lookback_days: int, exclude_ids: set[str]) -> list[dict]:
    """近幾天入庫但從未進過每日精選的文章，補進今日候選池。

    必須排除本次剛寫入的 id，否則同一篇會同時出現在兩邊，
    佔用兩個名次並違反 UNIQUE(digest_date, article_id)。
    """
    picked_ids = db.query(models.NewsDailyDigest.article_id)
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    q = (db.query(models.NewsArticle, models.NewsSource.slug)
         .join(models.NewsSource, models.NewsSource.id == models.NewsArticle.source_id)
         .filter(models.NewsArticle.collected_at >= cutoff,
                 models.NewsArticle.is_deleted.is_(False),
                 models.NewsArticle.status == models.NewsArticleStatus.active,
                 ~models.NewsArticle.id.in_(picked_ids)))
    if exclude_ids:
        q = q.filter(~models.NewsArticle.id.in_(list(exclude_ids)))
    rows = q.order_by(models.NewsArticle.rank_score.desc()).limit(80).all()

    return [{
        "article": a,
        "source_slug": slug,
        "rank_score": float(a.rank_score or 0),
        "is_safety_signal": bool(a.is_safety_signal),
        "evidence_maturity": a.evidence_maturity.value if a.evidence_maturity else "unknown",
    } for a, slug in rows]


def _pick_reason(p: dict) -> str:
    bits = []
    if p["is_safety_signal"]:
        bits.append("含安全／交互作用訊號")
    bits.append({
        "human": "human：涉及人體研究",
        "mixed": "mixed：含人體與臨床前資料",
        "preclinical": "preclinical：臨床前研究，不可推論至病患",
        "unknown": "unknown：證據層級未明",
    }.get(p["evidence_maturity"], "unknown"))
    src = SOURCE_BY_SLUG.get(p["source_slug"])
    if src:
        bits.append(f"來源權威度 {src.weight:.2f}")
    bits.append(f"綜合分數 {p['rank_score']:.3f}")
    return "；".join(bits)


def _auto_archive(db: Session, days: int) -> int:
    cutoff = datetime.utcnow() - timedelta(days=days)
    bookmarked = db.query(models.UserNewsBookmark.article_id)
    n = (db.query(models.NewsArticle)
         .filter(models.NewsArticle.collected_at < cutoff,
                 models.NewsArticle.status == models.NewsArticleStatus.active,
                 models.NewsArticle.is_deleted.is_(False),
                 ~models.NewsArticle.id.in_(bookmarked))
         .update({models.NewsArticle.status: models.NewsArticleStatus.archived},
                 synchronize_session=False))
    return n or 0


def _update_source_health(db: Session, slug_to_id: dict[str, str], stats: dict) -> None:
    now = datetime.utcnow()
    for slug, st in stats.items():
        sid = slug_to_id.get(slug)
        if not sid:
            continue
        row = db.query(models.NewsSource).filter(models.NewsSource.id == sid).first()
        if not row:
            continue
        if st.get("error"):
            row.last_error = str(st["error"])[:2000]
            row.consecutive_failures = (row.consecutive_failures or 0) + 1
        else:
            row.last_success_at = now
            row.last_error = None
            row.consecutive_failures = 0
    db.flush()


# ---------------------------------------------------------------------------
# 多語系簡短摘要（news_article_summaries）
#
# 產生策略刻意是「隨選 + 快取」而不是「收集時把所有語系一次做完」：
# 每天 10 篇 × 4 個語系 = 40 次生成，但實際上絕大多數使用者只看一種語系，
# 其餘語系的費用等於丟進水裡。改成「有人真的用那個語系開這一頁，才產生並存起來」，
# 冷門語系完全不花錢，而熱門語系只在第一次被看到時付一次。
# ---------------------------------------------------------------------------
def _summary_char_limit(db: Session) -> int:
    cfg = get_settings(db)
    raw = cfg.get("summary_length", short_summary.DEFAULT_CHAR_LIMIT)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = short_summary.DEFAULT_CHAR_LIMIT
    return max(short_summary.MIN_CHAR_LIMIT, min(short_summary.MAX_CHAR_LIMIT, value))


def _article_payload(db: Session, article: models.NewsArticle) -> dict:
    src = db.query(models.NewsSource).filter(
        models.NewsSource.id == article.source_id).first()
    return {
        "title": article.title,
        "abstract": article.abstract,
        "summary_zh": article.summary_zh,
        "journal": article.journal,
        "study_design": article.study_design,
        "source_name": src.name_zh if src else None,
        "evidence_maturity": (article.evidence_maturity.value
                              if article.evidence_maturity else "unknown"),
        "is_safety_signal": bool(article.is_safety_signal),
    }


def get_summaries(db: Session, article_ids: list[str], lang: str, *,
                  generate_missing: bool = False, max_generate: int = 12) -> dict[str, dict]:
    """取得指定語系的簡短摘要。回傳 {article_id: {summary, is_ai, stale}}。

    `generate_missing=False`（預設）只讀快取，讓 /news/daily 這種每次載入都會打的端點
    保持「不會因為要產摘要而變慢」；真正的生成走專門的批次端點。

    字數上限改過之後，舊摘要不會自動重產（那會在管理者一改設定就引發大量 API 呼叫），
    但會標成 stale=True，讓後台知道哪些可以回補。
    """
    if not article_ids or lang not in short_summary.SUMMARY_LANGS:
        return {}
    limit = _summary_char_limit(db)
    rows = (db.query(models.NewsArticleSummary)
            .filter(models.NewsArticleSummary.article_id.in_(article_ids),
                    models.NewsArticleSummary.lang == lang)
            .all())
    out = {r.article_id: {"summary": r.summary, "is_ai": bool(r.is_ai),
                          "stale": r.char_limit != limit} for r in rows}

    if not generate_missing:
        return out

    missing = [aid for aid in article_ids if aid not in out][:max_generate]
    if not missing:
        return out

    articles = (db.query(models.NewsArticle)
                .filter(models.NewsArticle.id.in_(missing)).all())
    if not articles:
        return out

    payloads = [_article_payload(db, a) for a in articles]
    generated = short_summary.generate(payloads, lang, limit)

    for article, result in zip(articles, generated):
        text = result.get("summary")
        if not text:
            continue          # 例如韓文又沒有 API key：不寫入空列，留待日後補產
        db.add(models.NewsArticleSummary(
            article_id=article.id, lang=lang, summary=text, char_limit=limit,
            is_ai=bool(result.get("is_ai")), model=result.get("model"),
        ))
        out[article.id] = {"summary": text, "is_ai": bool(result.get("is_ai")),
                           "stale": False}
    db.commit()
    return out


def backfill_summaries(db: Session, lang: str, *, days: int = 30, limit: int = 30,
                       include_stale: bool = False) -> dict:
    """後台「回補摘要」：把還沒有該語系摘要的舊文章補上。

    有 limit 上限是刻意的——一次回補上千篇會讓請求逾時、費用也不受控。
    管理者按幾次就補幾批，回傳值會告訴他還剩幾篇。
    """
    if lang not in short_summary.SUMMARY_LANGS:
        raise ValueError(f"不支援的摘要語系：{lang}")
    cutoff = datetime.utcnow() - timedelta(days=days)
    char_limit = _summary_char_limit(db)

    have = db.query(models.NewsArticleSummary.article_id).filter(
        models.NewsArticleSummary.lang == lang)
    if include_stale:
        have = have.filter(models.NewsArticleSummary.char_limit == char_limit)

    todo_q = (db.query(models.NewsArticle)
              .filter(models.NewsArticle.is_deleted.is_(False),
                      models.NewsArticle.collected_at >= cutoff,
                      ~models.NewsArticle.id.in_(have))
              .order_by(models.NewsArticle.collected_at.desc()))
    remaining = todo_q.count()
    articles = todo_q.limit(limit).all()
    if not articles:
        return {"lang": lang, "processed": 0, "written": 0, "remaining": 0,
                "char_limit": char_limit}

    payloads = [_article_payload(db, a) for a in articles]
    generated = short_summary.generate(payloads, lang, char_limit)

    written = 0
    for article, result in zip(articles, generated):
        text = result.get("summary")
        if not text:
            continue
        existing = (db.query(models.NewsArticleSummary)
                    .filter(models.NewsArticleSummary.article_id == article.id,
                            models.NewsArticleSummary.lang == lang).first())
        if existing:                      # include_stale 的重產路徑
            existing.summary = text
            existing.char_limit = char_limit
            existing.is_ai = bool(result.get("is_ai"))
            existing.model = result.get("model")
            existing.generated_at = datetime.utcnow()
        else:
            db.add(models.NewsArticleSummary(
                article_id=article.id, lang=lang, summary=text, char_limit=char_limit,
                is_ai=bool(result.get("is_ai")), model=result.get("model"),
            ))
        written += 1
    db.commit()
    return {"lang": lang, "processed": len(articles), "written": written,
            "remaining": max(0, remaining - written), "char_limit": char_limit}
