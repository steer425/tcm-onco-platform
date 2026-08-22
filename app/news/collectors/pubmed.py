"""PubMed 收集器 — NCBI E-utilities（esearch → efetch）。

依 NCBI 使用規範：
  * 帶上 tool + email
  * 無 api_key 時 ≤3 req/s，有 key 時 ≤10 req/s
  * 大量查詢請於美東離峰時段執行（本模組排在 Asia/Taipei 04:00 = 美東 16:00 前一日，
    屬可接受區間；若量體變大建議申請 api_key）
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from .base import BaseCollector, CollectorError, RawItem

logger = logging.getLogger(__name__)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class PubMedCollector(BaseCollector):
    async def fetch(self) -> list[RawItem]:
        cfg = self.source.config
        api_key = cfg.get("api_key")
        rate = cfg.get("rate_limit_per_sec", 10 if api_key else 3)
        delay = 1.0 / max(rate, 1)

        common = {
            "db": cfg["db"],
            "tool": cfg.get("tool", "grace-tcm-news"),
            "email": self.contact_email,
        }
        if api_key:
            common["api_key"] = api_key

        # ---- 1) esearch 取得 PMID 清單 --------------------------------
        search_params = {
            **common,
            "term": cfg["query"],
            "retmode": "json",
            "retmax": cfg.get("retmax", 120),
            "sort": "date",
            "datetype": cfg.get("datetype", "edat"),
            "reldate": cfg.get("reldate_days", self.lookback_days),
        }
        resp = await self.get(cfg["esearch"], params=search_params, expect_json=True)
        payload = resp.json()
        pmids: list[str] = payload.get("esearchresult", {}).get("idlist", [])
        if not pmids:
            logger.info("[pubmed] no new records in window")
            return []

        # ---- 2) efetch 取詳細 XML（分批 100 筆）----------------------
        items: list[RawItem] = []
        for chunk_start in range(0, len(pmids), 100):
            chunk = pmids[chunk_start:chunk_start + 100]
            await asyncio.sleep(delay)
            fetch_params = {
                **common,
                "id": ",".join(chunk),
                "retmode": "xml",
                "rettype": "abstract",
            }
            fresp = await self.get(cfg["efetch"], params=fetch_params)
            try:
                root = ET.fromstring(fresp.text)
            except ET.ParseError as exc:
                raise CollectorError(f"pubmed efetch XML parse error: {exc}") from exc
            for art in root.findall(".//PubmedArticle"):
                item = self._parse_article(art, cfg)
                if item:
                    items.append(item)
        return items

    # ------------------------------------------------------------------
    def _parse_article(self, art: ET.Element, cfg: dict) -> RawItem | None:
        pmid_el = art.find(".//PMID")
        if pmid_el is None or not pmid_el.text:
            return None
        pmid = pmid_el.text.strip()

        title = _text(art.find(".//ArticleTitle")) or f"PMID {pmid}"

        # 摘要可能被拆成多個 labelled section
        abstract_parts: list[str] = []
        for ab in art.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            body = _text(ab)
            if not body:
                continue
            abstract_parts.append(f"{label}: {body}" if label else body)
        abstract = "\n".join(abstract_parts) or None

        journal = _text(art.find(".//Journal/Title"))
        doi = None
        for aid in art.findall(".//ArticleId"):
            if aid.get("IdType") == "doi" and aid.text:
                doi = aid.text.strip()
                break

        authors: list[str] = []
        for a in art.findall(".//AuthorList/Author")[:8]:
            last, initials = _text(a.find("LastName")), _text(a.find("Initials"))
            if last:
                authors.append(f"{last} {initials}".strip())
        author_str = ", ".join(authors) + (" et al." if len(authors) >= 8 else "")

        pub_types = [
            _text(pt) for pt in art.findall(".//PublicationTypeList/PublicationType")
        ]
        pub_types = [p for p in pub_types if p]
        high_value = set(cfg.get("high_value_pubtypes", []))
        design = next((p for p in pub_types if p in high_value), None)
        if design is None and pub_types:
            design = next(
                (p for p in pub_types if p not in ("Journal Article", "Review")),
                pub_types[0],
            )

        published = _parse_pub_date(art)

        return RawItem(
            source_slug=self.source.slug,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            title=title,
            abstract=abstract,
            published_at=published,
            external_id=pmid,
            doi=doi,
            authors=author_str or None,
            journal=journal,
            lang="en",
            study_design=design,
            raw={"pmid": pmid, "publication_types": pub_types},
        )


# ----------------------------------------------------------------------
def _text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    return "".join(el.itertext()).strip() or None


def _parse_pub_date(art: ET.Element) -> datetime | None:
    """優先用 Entrez 入庫日（PubMedPubDate[PubStatus=entrez]），較貼近「新聞性」。"""
    for status in ("entrez", "pubmed", "medline"):
        el = art.find(f".//PubMedPubDate[@PubStatus='{status}']")
        if el is not None:
            try:
                return datetime(
                    int(_text(el.find("Year")) or 0),
                    int(_text(el.find("Month")) or 1),
                    int(_text(el.find("Day")) or 1),
                    tzinfo=timezone.utc,
                )
            except (TypeError, ValueError):
                continue

    pd = art.find(".//Journal/JournalIssue/PubDate")
    if pd is not None:
        year = _text(pd.find("Year"))
        if year and year.isdigit():
            month_raw = (_text(pd.find("Month")) or "1").lower()
            month = _MONTHS.get(month_raw[:3], int(month_raw) if month_raw.isdigit() else 1)
            day_raw = _text(pd.find("Day")) or "1"
            day = int(day_raw) if day_raw.isdigit() else 1
            try:
                return datetime(int(year), month, day, tzinfo=timezone.utc)
            except ValueError:
                return datetime(int(year), 1, 1, tzinfo=timezone.utc)
    return None
