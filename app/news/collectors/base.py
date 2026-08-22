"""收集器共用基礎：RawItem 資料結構、HTTP client、Collector 介面。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from ..sources import SourceDef

logger = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
BOT_UA = "GraceTCM-NewsBot/1.0 (research aggregator; +mailto:{contact})"

# URL 正規化時要丟掉的追蹤參數
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source", "_ga",
}


@dataclass
class RawItem:
    """各來源抓回來的統一中介格式，尚未經過分類/摘要。"""

    source_slug: str
    url: str
    title: str
    abstract: str | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    external_id: str | None = None       # PMID / NCT
    doi: str | None = None
    authors: str | None = None
    journal: str | None = None
    lang: str | None = None
    study_design: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    # ---- 去重用雜湊 -------------------------------------------------
    @property
    def url_hash(self) -> str:
        return hashlib.sha256(normalize_url(self.url).encode("utf-8")).hexdigest()

    @property
    def content_hash(self) -> str:
        basis = f"{_norm_text(self.title)}||{_norm_text(self.abstract or '')[:600]}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def normalize_url(url: str) -> str:
    """去除追蹤參數、統一 scheme/host 大小寫、去尾斜線與 fragment。"""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url.strip()
    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query = urlencode(
        [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
         if k.lower() not in _TRACKING_PARAMS]
    )
    path = p.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", query, ""))


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def simhash64(text: str) -> int:
    """標題 simhash，用於抓「同一則新聞不同轉載」的近似重複。

    採字元 shingle（英數 4-gram、中日韓 2-gram）而非詞元：
    標題偏短，詞元數少時單字差異（patient/patients）會造成過大的漢明距離，
    字元 shingle 特徵數多且重疊高，近似判斷穩定得多。
    """
    norm = re.sub(r"[^a-z0-9一-鿿]+", " ", _norm_text(text)).strip()
    if not norm:
        return 0

    grams: list[str] = []
    # 英數 4-gram（含空白，保留詞界資訊）
    latin = re.sub(r"[一-鿿]", "", norm)
    latin = re.sub(r"\s+", " ", latin).strip()
    if len(latin) >= 4:
        grams.extend(latin[i:i + 4] for i in range(len(latin) - 3))
    elif latin:
        grams.append(latin)
    # 中日韓 2-gram
    cjk = re.sub(r"[^一-鿿]", "", norm)
    if len(cjk) >= 2:
        grams.extend(cjk[i:i + 2] for i in range(len(cjk) - 1))
    elif cjk:
        grams.append(cjk)

    if not grams:
        return 0

    vector = [0] * 64
    for g in grams:
        h = int.from_bytes(hashlib.md5(g.encode()).digest()[:8], "big")
        for i in range(64):
            vector[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i, v in enumerate(vector):
        if v > 0:
            out |= 1 << i
    # 轉成有號 64-bit 以便存入 PostgreSQL BIGINT
    return out - (1 << 64) if out >= (1 << 63) else out


def hamming(a: int, b: int) -> int:
    return bin((a & 0xFFFFFFFFFFFFFFFF) ^ (b & 0xFFFFFFFFFFFFFFFF)).count("1")


class CollectorError(Exception):
    """來源抓取失敗；allow_failure=True 的來源不會中斷整體流程。"""


class BaseCollector:
    """所有收集器的父類別。子類別實作 `fetch()`。"""

    def __init__(
        self,
        source: SourceDef,
        client: httpx.AsyncClient,
        *,
        contact_email: str = "research@example.org",
        lookback_days: int = 3,
    ) -> None:
        self.source = source
        self.client = client
        self.contact_email = contact_email
        self.lookback_days = int(source.config.get("lookback_days", lookback_days))

    # ------------------------------------------------------------------
    @property
    def cutoff(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=self.lookback_days)

    def headers(self) -> dict[str, str]:
        if self.source.config.get("requires_browser_ua"):
            ua = BROWSER_UA
        else:
            ua = BOT_UA.format(contact=self.contact_email)
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml,"
                      "application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        retries: int = 3,
        expect_json: bool = False,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = await self.client.get(
                    url, params=params, headers=self.headers(), timeout=30.0,
                    follow_redirects=True,
                )
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise CollectorError(f"HTTP {resp.status_code} from {url}")
                resp.raise_for_status()
                if expect_json:
                    resp.json()  # 早期驗證
                return resp
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = min(2 ** attempt, 8) + (attempt * 0.3)
                logger.warning(
                    "[%s] fetch failed (%s/%s) %s: %s",
                    self.source.slug, attempt + 1, retries, url, exc,
                )
                if attempt < retries - 1:
                    await asyncio.sleep(wait)
        raise CollectorError(f"{self.source.slug}: {url} failed — {last_exc}") from last_exc

    # ------------------------------------------------------------------
    async def fetch(self) -> list[RawItem]:  # pragma: no cover - 抽象
        raise NotImplementedError

    async def safe_fetch(self) -> tuple[list[RawItem], str | None]:
        """回傳 (items, error)。allow_failure 的來源失敗時不拋例外。"""
        try:
            items = await self.fetch()
            # 統一套用時間下界
            kept = [
                it for it in items
                if it.published_at is None or it.published_at >= self.cutoff
            ]
            logger.info(
                "[%s] fetched=%s kept=%s", self.source.slug, len(items), len(kept)
            )
            return kept, None
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"
            if self.source.config.get("allow_failure"):
                logger.error("[%s] failed (tolerated): %s", self.source.slug, msg)
                return [], msg
            logger.exception("[%s] failed", self.source.slug)
            return [], msg
