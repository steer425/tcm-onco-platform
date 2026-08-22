"""HTML 爬蟲收集器 — NCCIH、OCCAM、MSK、About Herbs、NHC、SATCM。

設計原則：
  * 選擇器寫在來源 config，改版時只需改設定不需改程式。
  * 尊重 robots.txt（可用 respect_robots=False 關閉，預設開啟）。
  * About Herbs 這類「資料庫而非新聞流」的來源走 content_change 模式：
    比對條目內容雜湊，有變動才視為新事件。
  * 中國官方站設 allow_failure=True，連線失敗不阻斷當日流程。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from .base import BaseCollector, CollectorError, RawItem, normalize_url

logger = logging.getLogger(__name__)

_DATE_PATTERNS = [
    (re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})"), "ymd"),
    (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), "mdy"),
    (re.compile(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})", re.I), "Mdy"),
]
_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


class HTMLScrapeCollector(BaseCollector):
    def __init__(self, *args, respect_robots: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.respect_robots = respect_robots
        self._robots: dict[str, RobotFileParser | None] = {}

    # ------------------------------------------------------------------
    async def fetch(self) -> list[RawItem]:
        cfg = self.source.config
        list_urls: list[str] = cfg.get("list_urls") or (
            [cfg["list_url"]] if cfg.get("list_url") else []
        )
        if not list_urls:
            raise CollectorError(f"{self.source.slug}: no list_urls configured")

        items: dict[str, RawItem] = {}
        errors: list[str] = []

        for list_url in list_urls:
            if self.respect_robots and not await self._allowed(list_url):
                logger.info("[%s] robots.txt disallows %s", self.source.slug, list_url)
                continue
            try:
                resp = await self.get(list_url)
                encoding = cfg.get("encoding")
                html = resp.content.decode(encoding, errors="replace") if encoding else resp.text
                items.update(self._parse_list(html, list_url, cfg))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{list_url}: {exc}")
                logger.warning("[%s] list failed %s: %s", self.source.slug, list_url, exc)
            await asyncio.sleep(0.6)

        if not items and errors:
            raise CollectorError("; ".join(errors))

        # content_change 模式：抓內文雜湊（About Herbs）
        if cfg.get("track_mode") == "content_change":
            await self._attach_content_hashes(list(items.values()), cfg)

        return list(items.values())

    # ------------------------------------------------------------------
    def _parse_list(self, html: str, list_url: str, cfg: dict) -> dict[str, RawItem]:
        soup = BeautifulSoup(html, "html.parser")
        base = cfg.get("base") or f"{urlparse(list_url).scheme}://{urlparse(list_url).netloc}"
        selector = cfg.get("item_selector", "a[href]")
        must_contain: list[str] = cfg.get("link_must_contain", [])

        found: dict[str, RawItem] = {}
        for a in soup.select(selector):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            url = urljoin(base if href.startswith("/") else list_url, href)
            if urlparse(url).scheme not in ("http", "https"):
                continue
            if must_contain and not any(tok in url for tok in must_contain):
                continue

            title = _clean(a.get_text(" ", strip=True)) or _clean(a.get("title", ""))
            if not title or len(title) < 8:
                continue

            published = self._extract_date(a, cfg)
            key = normalize_url(url)
            if key in found:
                continue
            found[key] = RawItem(
                source_slug=self.source.slug,
                url=url,
                title=title,
                published_at=published,
                lang=self.source.lang,
                raw={"list_url": list_url},
            )
        return found

    # ------------------------------------------------------------------
    def _extract_date(self, anchor, cfg: dict) -> datetime | None:
        date_selector = cfg.get("date_selector")
        candidates: list[str] = []

        # 先找同層／父層的日期節點
        containers = [anchor]
        parent = anchor.parent
        for _ in range(3):
            if parent is None:
                break
            containers.append(parent)
            parent = parent.parent

        for node in containers:
            if date_selector:
                for d in node.select(date_selector):
                    dt_attr = d.get("datetime")
                    if dt_attr:
                        candidates.append(dt_attr)
                    candidates.append(d.get_text(" ", strip=True))
            candidates.append(node.get_text(" ", strip=True)[:200])

        for text in candidates:
            dt = _parse_any_date(text)
            if dt:
                return dt
        return None

    # ------------------------------------------------------------------
    async def _attach_content_hashes(self, items: list[RawItem], cfg: dict) -> None:
        """About Herbs：抓每個條目內文，算雜湊放進 raw，供 service 判斷是否更新。"""
        selector = cfg.get("content_hash_selector", "main")
        limit = cfg.get("content_fetch_limit", 40)
        for item in items[:limit]:
            try:
                resp = await self.get(item.url, retries=2)
                soup = BeautifulSoup(resp.text, "html.parser")
                node = soup.select_one(selector) or soup
                body = _clean(node.get_text(" ", strip=True))[:20000]
                item.abstract = body[:1200] or item.abstract
                item.raw["body_hash"] = hashlib.sha256(body.encode()).hexdigest()
                item.raw["track_mode"] = "content_change"
            except Exception as exc:  # noqa: BLE001
                logger.debug("[%s] content fetch failed %s: %s",
                             self.source.slug, item.url, exc)
            await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    async def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp: RobotFileParser | None = None
            try:
                resp = await self.get(f"{origin}/robots.txt", retries=1)
                rp = RobotFileParser()
                rp.parse(resp.text.splitlines())
            except Exception:  # noqa: BLE001
                rp = None  # 取不到 robots.txt 視為允許
            self._robots[origin] = rp
        rp = self._robots[origin]
        return True if rp is None else rp.can_fetch(self.headers()["User-Agent"], url)


# ----------------------------------------------------------------------
def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _parse_any_date(text: str) -> datetime | None:
    if not text:
        return None
    # ISO datetime 屬性
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for pattern, kind in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif kind == "mdy":
                mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                mo = _MONTH_NAMES[m.group(1).lower()]
                d, y = int(m.group(2)), int(m.group(3))
            if not (1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
                continue
            return datetime(y, mo, d, tzinfo=timezone.utc)
        except (ValueError, KeyError):
            continue
    return None
