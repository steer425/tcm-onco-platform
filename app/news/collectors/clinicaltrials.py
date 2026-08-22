"""ClinicalTrials.gov 收集器 — 官方 REST API v2。

2026-08 實測：
  GET https://clinicaltrials.gov/api/v2/studies
      ?query.cond=cancer&query.intr=chinese+herbal+medicine
      &pageSize=2&fields=NCTId,BriefTitle,OverallStatus,LastUpdatePostDate
  → {"studies":[{"protocolSection":{...}}], "nextPageToken": "..."}

依 docx 提醒：登錄不等於有效，因此我們一併帶出 status / phase / enrollment /
主要終點資訊，讓前台能標示「僅為登錄，尚無結果」。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .base import BaseCollector, RawItem

logger = logging.getLogger(__name__)


class ClinicalTrialsCollector(BaseCollector):
    async def fetch(self) -> list[RawItem]:
        cfg = self.source.config
        seen: dict[str, RawItem] = {}

        for intervention in cfg["intervention_queries"]:
            try:
                studies = await self._query(intervention, cfg)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[clinicaltrials] '%s' failed: %s", intervention, exc)
                continue
            for study in studies:
                item = self._parse(study, intervention)
                if item and item.external_id not in seen:
                    seen[item.external_id] = item
            await asyncio.sleep(0.4)  # 對公用 API 保守節流

        return list(seen.values())

    # ------------------------------------------------------------------
    async def _query(self, intervention: str, cfg: dict) -> list[dict]:
        params = {
            "query.cond": cfg["condition"],
            "query.intr": intervention,
            "pageSize": cfg.get("page_size", 50),
            "fields": ",".join(cfg["fields"]),
            # 依最後更新排序，才抓得到「今天有變動」的試驗
            "sort": "LastUpdatePostDate:desc",
        }
        resp = await self.get(cfg["base_url"], params=params, expect_json=True)
        return resp.json().get("studies", [])

    # ------------------------------------------------------------------
    def _parse(self, study: dict, matched_intervention: str) -> RawItem | None:
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        nct = ident.get("nctId")
        if not nct:
            return None

        status_mod = proto.get("statusModule", {})
        design_mod = proto.get("designModule", {})
        cond_mod = proto.get("conditionsModule", {})
        arms_mod = proto.get("armsInterventionsModule", {})
        desc_mod = proto.get("descriptionModule", {})
        sponsor_mod = proto.get("sponsorCollaboratorsModule", {})

        last_update = _date(status_mod.get("lastUpdatePostDateStruct", {}).get("date"))
        first_post = _date(status_mod.get("studyFirstPostDateStruct", {}).get("date"))

        overall_status = status_mod.get("overallStatus")
        phases = design_mod.get("phases") or []
        enrollment = (design_mod.get("enrollmentInfo") or {}).get("count")
        allocation = (design_mod.get("designInfo") or {}).get("allocation")
        masking = ((design_mod.get("designInfo") or {}).get("maskingInfo") or {}).get("masking")

        interventions = [
            f"{i.get('type','')}: {i.get('name','')}".strip(": ")
            for i in (arms_mod.get("interventions") or [])
        ]

        design_bits = [p for p in phases]
        if allocation:
            design_bits.append(allocation)
        if masking:
            design_bits.append(f"{masking} masking")
        study_design = " / ".join(design_bits) or None

        # 摘要前面加上關鍵狀態，讓 AI 摘要與前台都能立刻標示證據成熟度
        header = (
            f"[Status: {overall_status or 'UNKNOWN'}]"
            f"[Phase: {', '.join(phases) if phases else 'N/A'}]"
            f"[Enrollment: {enrollment if enrollment is not None else 'N/A'}]"
        )
        brief = desc_mod.get("briefSummary") or ""
        abstract = f"{header}\n{brief}".strip()

        return RawItem(
            source_slug=self.source.slug,
            url=f"https://clinicaltrials.gov/study/{nct}",
            title=ident.get("briefTitle") or ident.get("officialTitle") or nct,
            abstract=abstract or None,
            published_at=last_update or first_post,
            source_updated_at=last_update,
            external_id=nct,
            journal=(sponsor_mod.get("leadSponsor") or {}).get("name"),
            lang="en",
            study_design=study_design,
            raw={
                "nct_id": nct,
                "overall_status": overall_status,
                "phases": phases,
                "enrollment": enrollment,
                "allocation": allocation,
                "masking": masking,
                "conditions": cond_mod.get("conditions") or [],
                "interventions": interventions,
                "matched_intervention": matched_intervention,
                "study_first_post": first_post.isoformat() if first_post else None,
            },
        )


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
