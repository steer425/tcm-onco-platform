"""主題過濾、分類標註與每日排序評分。

排序哲學（呼應 docx 的「使用原則」）：
  1. 安全訊號（交互作用、毒性、警訊）優先 — 平台定位是安全監測與證據查證。
  2. 人體證據 > 動物/細胞/計算預測。標題若只是細胞毒殺或分子對接，降權。
  3. 來源權威度與時效性次之。
  4. 單一來源每日入選上限，避免 PubMed 洗版。
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from .collectors.base import RawItem
from .sources import CANCER_TERMS, SAFETY_TERMS, SOURCE_BY_SLUG, TCM_TERMS

# ----------------------------------------------------------------------
# 癌別與介入方式辨識
# ----------------------------------------------------------------------
CANCER_TYPE_MAP: dict[str, list[str]] = {
    "lung":        ["lung cancer", "nsclc", "sclc", "肺癌", "肺腺癌"],
    "breast":      ["breast cancer", "乳癌", "乳腺癌"],
    "liver":       ["hepatocellular", "liver cancer", "hcc", "肝癌"],
    "gastric":     ["gastric cancer", "stomach cancer", "胃癌"],
    "colorectal":  ["colorectal", "colon cancer", "rectal cancer", "大腸癌", "結直腸癌", "结直肠癌"],
    "esophageal":  ["esophageal", "oesophageal", "食道癌", "食管癌"],
    "pancreatic":  ["pancreatic", "胰腺癌", "胰臟癌"],
    "prostate":    ["prostate cancer", "攝護腺癌", "前列腺癌"],
    "ovarian":     ["ovarian cancer", "卵巢癌"],
    "cervical":    ["cervical cancer", "子宮頸癌", "宫颈癌"],
    "nasopharyngeal": ["nasopharyngeal", "鼻咽癌"],
    "leukemia":    ["leukemia", "leukaemia", "白血病"],
    "lymphoma":    ["lymphoma", "淋巴瘤"],
    "glioma":      ["glioma", "glioblastoma", "膠質瘤", "胶质瘤"],
    "melanoma":    ["melanoma", "黑色素瘤"],
    "renal":       ["renal cell", "kidney cancer", "腎癌", "肾癌"],
    "bladder":     ["bladder cancer", "膀胱癌"],
    "head_neck":   ["head and neck cancer", "頭頸癌", "头颈癌"],
}

INTERVENTION_MAP: dict[str, list[str]] = {
    "herbal_formula":   ["decoction", "formula", "granule", "tang", "湯", "汤", "方劑", "方剂", "顆粒", "颗粒"],
    "single_herb":      ["extract of", "single herb", "單味", "单味", "飲片", "饮片"],
    "compound":         ["curcumin", "berberine", "artemisinin", "ginsenoside", "baicalein",
                         "quercetin", "resveratrol", "triptolide", "emodin", "tanshinone",
                         "薑黃素", "小檗鹼", "青蒿素", "人參皂苷", "皂苷"],
    "acupuncture":      ["acupuncture", "electroacupuncture", "acupressure", "針灸", "针灸", "穴位"],
    "injection":        ["injection", "注射液", "注射劑"],
    "mind_body":        ["tai chi", "qigong", "meditation", "yoga", "太極", "太极", "氣功", "气功"],
    "supplement":       ["dietary supplement", "nutraceutical", "膳食補充", "保健食品"],
}

# 降權：非人體證據（依 docx「重要提醒」）
PRECLINICAL_TERMS = [
    "in vitro", "cell line", "cytotoxic", "molecular docking", "network pharmacology",
    "xenograft", "mouse model", "murine", "rat model", "zebrafish", "in silico",
    "細胞毒", "分子對接", "网络药理", "網絡藥理", "動物模型", "动物模型",
]

# 加權：人體證據
CLINICAL_TERMS = [
    "randomized", "randomised", "double-blind", "placebo-controlled",
    "systematic review", "meta-analysis", "clinical trial", "cohort",
    "phase ii", "phase iii", "patients", "participants",
    "隨機", "随机", "雙盲", "双盲", "安慰劑", "安慰剂", "系統性回顧", "系统评价", "臨床試驗", "临床试验",
]

_STUDY_DESIGN_WEIGHT = {
    "meta-analysis": 1.00,
    "systematic review": 0.95,
    "randomized controlled trial": 0.95,
    "practice guideline": 0.90,
    "clinical trial, phase iii": 0.90,
    "clinical trial, phase ii": 0.80,
    "clinical trial": 0.70,
    "observational study": 0.55,
    "review": 0.45,
    "case reports": 0.30,
}


# ----------------------------------------------------------------------
def _hits(text: str, terms: list[str]) -> list[str]:
    return [t for t in terms if t in text]


def _blob(item: RawItem) -> str:
    return f"{item.title}\n{item.abstract or ''}\n{item.journal or ''}".lower()


def relevance(item: RawItem) -> float:
    """0..1 主題相關度：中藥/天然物 × 腫瘤。"""
    src = SOURCE_BY_SLUG.get(item.source_slug)
    text = _blob(item)
    cancer = _hits(text, CANCER_TERMS)
    tcm = _hits(text, TCM_TERMS)

    if src and src.prefiltered:
        # 來源本身鎖定主題（PubMed 查詢式、CT.gov 介入查詢、OCCAM、About Herbs）
        base = 0.70
        base += min(len(cancer), 3) * 0.05
        base += min(len(tcm), 3) * 0.05
        return min(base, 1.0)

    if not cancer or not tcm:
        # 兩個面向缺一即視為不相關，交由門檻濾掉
        return 0.0

    score = 0.45
    score += min(len(cancer), 4) * 0.06
    score += min(len(tcm), 4) * 0.07
    # 標題就命中，比只在內文命中更相關
    title_low = item.title.lower()
    if any(t in title_low for t in CANCER_TERMS) and any(t in title_low for t in TCM_TERMS):
        score += 0.15
    return min(score, 1.0)


def classify(item: RawItem) -> dict:
    """回傳分類標註：癌別、介入方式、安全訊號、證據成熟度。"""
    text = _blob(item)

    cancer_types = [k for k, terms in CANCER_TYPE_MAP.items() if _hits(text, terms)]
    interventions = [k for k, terms in INTERVENTION_MAP.items() if _hits(text, terms)]

    # CT.gov 直接用結構化欄位補強
    raw = item.raw or {}
    for cond in raw.get("conditions", []) or []:
        low = cond.lower()
        for k, terms in CANCER_TYPE_MAP.items():
            if any(t in low for t in terms) and k not in cancer_types:
                cancer_types.append(k)

    safety_hits = _hits(text, SAFETY_TERMS)
    src = SOURCE_BY_SLUG.get(item.source_slug)
    is_safety = bool(safety_hits) or (src is not None and src.slug == "msk_about_herbs")

    preclinical = _hits(text, PRECLINICAL_TERMS)
    clinical = _hits(text, CLINICAL_TERMS)
    if clinical and not preclinical:
        maturity = "human"
    elif clinical and preclinical:
        maturity = "mixed"
    elif preclinical:
        maturity = "preclinical"
    else:
        maturity = "unknown"

    tags: list[str] = []
    if is_safety:
        tags.append("safety")
    if maturity == "preclinical":
        tags.append("preclinical")
    if maturity == "human":
        tags.append("human_evidence")
    if item.source_slug == "clinicaltrials":
        status = (raw.get("overall_status") or "").upper()
        if status in ("RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"):
            tags.append("recruiting")
        if status in ("COMPLETED",):
            tags.append("completed_trial")
        if status in ("TERMINATED", "WITHDRAWN", "SUSPENDED"):
            tags.append("halted_trial")

    return {
        "cancer_types": cancer_types,
        "intervention_types": interventions,
        "is_safety_signal": is_safety,
        "evidence_maturity": maturity,
        "safety_hits": safety_hits[:8],
        "tags": tags,
    }


def _design_weight(item: RawItem) -> float:
    design = (item.study_design or "").lower()
    for key, w in _STUDY_DESIGN_WEIGHT.items():
        if key in design:
            return w
    return 0.5


def _recency(item: RawItem, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    if item.published_at is None:
        return 0.5
    age_days = max((now - item.published_at).total_seconds() / 86400.0, 0.0)
    # 半衰期 5 天
    return math.exp(-age_days / 5.0)


def rank_score(item: RawItem, meta: dict, rel: float) -> float:
    """綜合排序分數（0..1）。"""
    src = SOURCE_BY_SLUG.get(item.source_slug)
    authority = src.weight if src else 0.5

    maturity_w = {
        "human": 1.00, "mixed": 0.75, "unknown": 0.60, "preclinical": 0.40
    }[meta["evidence_maturity"]]

    score = (
        0.30 * rel
        + 0.22 * authority
        + 0.20 * maturity_w
        + 0.16 * _design_weight(item)
        + 0.12 * _recency(item)
    )

    # 安全訊號加成：平台定位優先服務安全監測
    if meta["is_safety_signal"]:
        score = min(score + 0.12, 1.0)
    # 已終止/撤回的試驗仍值得知道，但不搶版面
    if "halted_trial" in meta["tags"]:
        score = max(score - 0.05, 0.0)

    return round(min(max(score, 0.0), 1.0), 4)


def select_daily(
    scored: list[dict],
    *,
    size: int = 10,
    max_per_source: int = 4,
    min_score: float = 0.0,
) -> list[dict]:
    """從候選池挑出每日 Top N，套用單一來源上限避免洗版。

    `scored` 每項需含 rank_score / source_slug / is_safety_signal。
    """
    # 防呆：同一篇文章可能同時來自「本次新增」與「近日未入選」兩個來源，
    # 這裡先依 article id 去重，避免同一篇佔用兩個名次（會撞 uq_digest_date_article）。
    def _key(cand: dict):
        art = cand.get("article")
        art_id = getattr(art, "id", None)
        return ("id", art_id) if art_id is not None else ("obj", id(art))

    deduped: dict = {}
    for cand in scored:
        k = _key(cand)
        if k not in deduped or cand["rank_score"] > deduped[k]["rank_score"]:
            deduped[k] = cand

    pool = sorted(
        (s for s in deduped.values() if s["rank_score"] >= min_score),
        key=lambda s: (-s["rank_score"], s["source_slug"]),
    )
    picked: list[dict] = []
    per_source: dict[str, int] = {}

    for cand in pool:
        if len(picked) >= size:
            break
        slug = cand["source_slug"]
        if per_source.get(slug, 0) >= max_per_source:
            continue
        picked.append(cand)
        per_source[slug] = per_source.get(slug, 0) + 1

    # 若因上限湊不滿 N 篇，放寬上限補齊
    if len(picked) < size:
        chosen = {_key(p) for p in picked}
        for cand in pool:
            if len(picked) >= size:
                break
            if _key(cand) not in chosen:
                picked.append(cand)
                chosen.add(_key(cand))

    # 安全訊號排前面（同分時）
    picked.sort(key=lambda s: (-int(s.get("is_safety_signal", False)), -s["rank_score"]))
    for i, p in enumerate(picked, start=1):
        p["rank"] = i
    return picked
