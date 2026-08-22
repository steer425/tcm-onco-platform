"""收集器註冊表 — 依 SourceDef.kind 派工到對應 collector。"""

from __future__ import annotations

import asyncio
import logging
from typing import Iterable

import httpx

from ..sources import SOURCES, CollectorKind, SourceDef
from .base import BaseCollector, RawItem, hamming, normalize_url, simhash64
from .clinicaltrials import ClinicalTrialsCollector
from .html_scraper import HTMLScrapeCollector
from .pubmed import PubMedCollector
from .rss import RSSCollector

logger = logging.getLogger(__name__)

__all__ = [
    "BaseCollector", "RawItem", "build_collector", "collect_all",
    "normalize_url", "simhash64", "hamming",
]

# 特定來源用專屬 collector，其餘依 kind 落到通用 collector
_SPECIAL: dict[str, type[BaseCollector]] = {
    "pubmed": PubMedCollector,
    "clinicaltrials": ClinicalTrialsCollector,
}

_BY_KIND: dict[CollectorKind, type[BaseCollector]] = {
    CollectorKind.RSS: RSSCollector,
    CollectorKind.SCRAPE: HTMLScrapeCollector,
}


def build_collector(
    source: SourceDef,
    client: httpx.AsyncClient,
    *,
    contact_email: str,
    lookback_days: int = 3,
) -> BaseCollector:
    cls = _SPECIAL.get(source.slug) or _BY_KIND.get(source.kind)
    if cls is None:
        raise ValueError(f"no collector for source {source.slug} (kind={source.kind})")
    return cls(
        source, client, contact_email=contact_email, lookback_days=lookback_days
    )


async def collect_all(
    *,
    contact_email: str,
    sources: Iterable[SourceDef] | None = None,
    lookback_days: int = 3,
    concurrency: int = 4,
    pubmed_api_key: str | None = None,
) -> tuple[list[RawItem], dict[str, dict]]:
    """並行抓取所有來源。回傳 (所有 RawItem, 各來源統計)。

    單一來源失敗不會中斷其他來源；統計中會帶 error 訊息供後台顯示。
    """
    source_list = list(sources if sources is not None else SOURCES)
    if pubmed_api_key:
        for s in source_list:
            if s.slug == "pubmed":
                s.config["api_key"] = pubmed_api_key

    stats: dict[str, dict] = {}
    all_items: list[RawItem] = []
    sem = asyncio.Semaphore(concurrency)

    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=8)
    async with httpx.AsyncClient(limits=limits, http2=False) as client:

        async def run(src: SourceDef) -> None:
            async with sem:
                collector = build_collector(
                    src, client,
                    contact_email=contact_email,
                    lookback_days=lookback_days,
                )
                items, error = await collector.safe_fetch()
                stats[src.slug] = {
                    "fetched": len(items),
                    "error": error,
                    "kind": src.kind.value,
                }
                all_items.extend(items)

        await asyncio.gather(*(run(s) for s in source_list))

    logger.info(
        "collect_all done: %s items from %s sources (%s errors)",
        len(all_items), len(source_list),
        sum(1 for v in stats.values() if v["error"]),
    )
    return all_items, stats
