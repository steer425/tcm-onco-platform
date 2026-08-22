"""RSS/Atom 收集器 — WHO、NCI。

以標準函式庫解析，避免額外相依；同時支援 RSS 2.0 與 Atom。
若 feed 全數失敗且來源設有 fallback_scrape，改走 HTML 爬蟲。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from .base import BaseCollector, CollectorError, RawItem

logger = logging.getLogger(__name__)

_ATOM = "{http://www.w3.org/2005/Atom}"
_DC = "{http://purl.org/dc/elements/1.1/}"


class RSSCollector(BaseCollector):
    async def fetch(self) -> list[RawItem]:
        cfg = self.source.config
        urls: list[str] = cfg.get("feed_urls") or (
            [cfg["feed_url"]] if cfg.get("feed_url") else []
        )
        if not urls:
            raise CollectorError(f"{self.source.slug}: no feed_url configured")

        items: list[RawItem] = []
        errors: list[str] = []
        for url in urls:
            try:
                resp = await self.get(url)
                items.extend(self._parse_feed(resp.text))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {exc}")
                logger.warning("[%s] feed failed %s: %s", self.source.slug, url, exc)

        if not items and errors:
            fallback = cfg.get("fallback_scrape")
            if fallback:
                logger.info("[%s] all feeds failed, using fallback scraper", self.source.slug)
                from .html_scraper import HTMLScrapeCollector

                shim = type(self.source)(
                    **{**self.source.__dict__, "config": fallback}
                )
                return await HTMLScrapeCollector(
                    shim, self.client,
                    contact_email=self.contact_email,
                    lookback_days=self.lookback_days,
                ).fetch()
            raise CollectorError("; ".join(errors))

        return items

    # ------------------------------------------------------------------
    def _parse_feed(self, text: str) -> list[RawItem]:
        try:
            root = ET.fromstring(text.encode("utf-8", errors="replace"))
        except ET.ParseError as exc:
            raise CollectorError(f"feed parse error: {exc}") from exc

        entries = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
        out: list[RawItem] = []
        for e in entries:
            title = _t(e.find("title")) or _t(e.find(f"{_ATOM}title"))
            link = _link(e)
            if not title or not link:
                continue
            desc = (
                _t(e.find("description"))
                or _t(e.find(f"{_ATOM}summary"))
                or _t(e.find(f"{_ATOM}content"))
            )
            published = _date(
                _t(e.find("pubDate"))
                or _t(e.find(f"{_DC}date"))
                or _t(e.find(f"{_ATOM}published"))
                or _t(e.find(f"{_ATOM}updated"))
            )
            guid = _t(e.find("guid")) or _t(e.find(f"{_ATOM}id"))
            out.append(
                RawItem(
                    source_slug=self.source.slug,
                    url=link,
                    title=_strip_html(title),
                    abstract=_strip_html(desc) if desc else None,
                    published_at=published,
                    lang=self.source.lang,
                    raw={"guid": guid},
                )
            )
        return out


# ----------------------------------------------------------------------
def _t(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    return ("".join(el.itertext()) or "").strip() or None


def _link(e: ET.Element) -> str | None:
    link = _t(e.find("link"))
    if link:
        return link
    for a in e.findall(f"{_ATOM}link"):
        rel = a.get("rel", "alternate")
        if rel == "alternate" and a.get("href"):
            return a.get("href")
    a = e.find(f"{_ATOM}link")
    return a.get("href") if a is not None else None


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    # RFC 822（WHO feed 用 "Wed, 25 Feb 2026 18:06:55 Z"）
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    # ISO 8601
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        return datetime(*map(int, m.groups()), tzinfo=timezone.utc)
    return None


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    s = _TAG_RE.sub(" ", s)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")):
        s = s.replace(a, b)
    return _WS_RE.sub(" ", s).strip()
