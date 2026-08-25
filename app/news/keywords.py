"""主題過濾關鍵字：程式碼預設值 + 資料庫覆寫。

`sources.py` 裡的 `CANCER_TERMS`／`TCM_TERMS` 是**預設值**，
第一次執行時會被種進 `news_keywords`，之後以資料庫為準。
管理者在後台增刪，不需要改程式重新部署——新增一個來源之後最常要調的就是這個。
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app import models

from .sources import CANCER_TERMS, TCM_TERMS

logger = logging.getLogger(__name__)

GROUPS = ("tcm", "cancer")
GROUP_LABEL = {"tcm": "中藥／天然物", "cancer": "腫瘤／癌症"}
_DEFAULTS = {"tcm": TCM_TERMS, "cancer": CANCER_TERMS}


def normalize(term: str) -> str:
    """統一小寫並壓掉多餘空白。

    比對時 `_blob()` 出來的文字本來就是小寫，關鍵字若混著大小寫會比不到，
    所以入庫前就正規化，而不是每次比對再處理。
    """
    return " ".join((term or "").split()).lower()


def seed_defaults(db: Session) -> int:
    """把程式碼的預設詞種進資料庫（冪等）。

    刻意只新增、不還原已被停用或刪除的詞——否則管理者每次重新部署後
    都會發現自己刪掉的詞又冒出來。這跟 feature_config 的
    「不覆蓋 show_frontend/show_backend」是同一個道理。
    """
    existing = {(k.group, k.term) for k in db.query(models.NewsKeyword).all()}
    added = 0
    for group, terms in _DEFAULTS.items():
        for term in terms:
            key = (group, normalize(term))
            if key in existing:
                continue
            db.add(models.NewsKeyword(group=group, term=key[1],
                                      is_default=True, is_enabled=True))
            existing.add(key)
            added += 1
    if added:
        db.commit()
    return added


def get_terms(db: Session) -> dict[str, list[str]]:
    """回傳 {'tcm': [...], 'cancer': [...]}，只含啟用中的詞。

    資料庫是空的（例如還沒種過）時退回程式碼預設值，
    絕不回傳空清單——兩組都空的話 relevance() 會判定所有文章都不相關，
    當天的收集會全軍覆沒而且沒有任何錯誤訊息。
    """
    out: dict[str, list[str]] = {g: [] for g in GROUPS}
    for row in (db.query(models.NewsKeyword)
                .filter(models.NewsKeyword.is_enabled.is_(True)).all()):
        if row.group in out:
            out[row.group].append(row.term)
    for group in GROUPS:
        if not out[group]:
            logger.warning("關鍵字群組 %s 是空的，退回程式碼預設值", group)
            out[group] = [normalize(t) for t in _DEFAULTS[group]]
    return out


def counts(db: Session) -> dict[str, dict[str, int]]:
    """每組的啟用／停用筆數，供後台顯示。"""
    out = {g: {"enabled": 0, "disabled": 0, "total": 0} for g in GROUPS}
    for row in db.query(models.NewsKeyword).all():
        if row.group not in out:
            continue
        out[row.group]["total"] += 1
        out[row.group]["enabled" if row.is_enabled else "disabled"] += 1
    return out
