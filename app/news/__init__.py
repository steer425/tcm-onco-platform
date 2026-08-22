"""每日重點新聞模組（中藥與腫瘤）。

定位：科研輔助情報工具，服務於證據查證、安全監測與研究追蹤，
      不作為醫療診斷或治療建議。
"""

from .service import DEFAULT_SETTINGS, get_settings, run_daily_collection, taipei_today

__all__ = ["DEFAULT_SETTINGS", "get_settings", "run_daily_collection", "taipei_today"]
