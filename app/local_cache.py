"""
唯讀模式的核心：把「TCMSP 藥材/疾病/靶點/成分」跟「暗黑基因」這些變動很少、
但關聯查詢很頻繁的參考資料，從最新一次成功的備份，還原成一份存在伺服器本機磁碟上的
獨立 SQLite 檔案，查詢站的關聯查詢改讀這份本機端檔案，不用每次都連去遠端的雲端資料庫
（Neon PostgreSQL）來回，藉此加快查詢速度。

啟用唯讀模式時，`system_settings.py` 的 `set_read_only_mode()` 會呼叫這裡的
`rebuild_local_cache()`，用最新一次成功備份的內容重新建立這份本機快取。

只快取「查詢站相關、變動很少」的資料表（TCMSP 全系列 + 暗黑基因），
不快取病患資料、帳號、DNA 資料這類會頻繁異動或高度敏感的資料——
唯讀模式底下這些資料本來就不可寫入，也沒有加速查詢的急迫性，
縮小快取範圍可以讓重建速度更快、佔用空間更小。
"""
import datetime
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models

LOCAL_CACHE_DB_PATH = Path(__file__).resolve().parent.parent / "backups" / "local_query_cache.db"

# 只快取這些查詢站相關的資料表，其餘（帳號/病患/DNA等）不快取
CACHED_TABLES = [
    "tcmsp_herbs",
    "tcmsp_diseases",
    "tcmsp_ingredients",
    "tcmsp_targets",
    "tcmsp_herb_ingredient",
    "tcmsp_ingredient_target",
    "tcmsp_target_disease",
    "dark_genes",
    "gencc_diseases",
    # v1.43.0：查詢站實際會讀到、但先前漏掉的參考資料表。少了它們，唯讀模式下
    # F1-7／F1-8 走 get_query_db 會直接 500（no such table）：
    #   system_settings          OB／DL 門檻（pathways.adme_thresholds）；只有主題與門檻這類設定，無帳號資料
    #   tcmsp_target_uniprot     靶點 → 基因符號（target_index）
    #   tcmsp_ingredient_pubchem 成分標準化結果（F1-7）
    #   depmap_*                 Step 6 細胞株依賴（F1-8）
    "system_settings",
    "tcmsp_target_uniprot",
    "tcmsp_ingredient_pubchem",
    "depmap_models",
    "depmap_gene_dependency",
    "depmap_gene_summary",
    "depmap_import_runs",
    # v1.48.0：Step 5 文獻證據（F1-9）。searched_by 只是使用者 id，API 不回傳。
    "literature_searches",
    "literature_evidence",
    # 新聞模組：每日重點新聞屬於「每天更新一次、供大量前台讀取」的參考資料，適合快取。
    # 刻意不快取 user_news_bookmarks（使用者個人收藏，綁 users 外鍵）與 news_settings
    # （管理設定，讀取量小），維持「不快取帳號/使用者相關資料」的既有原則。
    "news_sources",
    "news_articles",
    "news_article_entities",
    "news_daily_digests",
]

_local_engine = None
_LocalSessionLocal = None


def _get_local_engine():
    global _local_engine, _LocalSessionLocal
    if _local_engine is None:
        _local_engine = create_engine(f"sqlite:///{LOCAL_CACHE_DB_PATH}", connect_args={"check_same_thread": False})
        _LocalSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_local_engine)
    return _local_engine


def get_local_cache_session():
    """給查詢端點用的 session，指向本機端快取 SQLite 檔案。呼叫前務必先確認 is_local_cache_available()。"""
    _get_local_engine()
    return _LocalSessionLocal()


def is_local_cache_available() -> bool:
    return LOCAL_CACHE_DB_PATH.exists()


def rebuild_local_cache(latest_backup_job) -> int:
    """從最新一次成功備份的加密內容，重新建立本機端查詢快取。回傳寫入的資料列總數。

    v1.48.2：還原邏輯（日期字串轉回 datetime、略過多餘欄位）改呼叫 `backup_restore.restore_dump()`，
    與命令列還原工具共用同一份，只是限定 CACHED_TABLES。
    """
    from app.backup_restore import restore_dump

    if not latest_backup_job or not latest_backup_job.file_path:
        raise ValueError("找不到可用的備份紀錄，無法建立本機端快取")

    if not os.path.exists(latest_backup_job.file_path):
        raise ValueError("最新一次備份的檔案已不在伺服器上（Render 部署或重啟後會清空），請先重新建立一次備份")

    LOCAL_CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_CACHE_DB_PATH.exists():
        LOCAL_CACHE_DB_PATH.unlink()  # 每次重建都整個重新來，避免舊資料殘留造成不一致

    global _local_engine, _LocalSessionLocal
    _local_engine = None  # 強制下次 _get_local_engine() 重新建立連線，指向剛清空重建的檔案
    engine = _get_local_engine()

    # 直接從檔案逐段讀（v1.48.3）：整份載入記憶體在 Render 免費方案會撐爆
    rep = restore_dump(engine, latest_backup_job.file_path, tables=CACHED_TABLES, require_empty=False)
    return sum(v["in_target"] for v in rep["tables"].values())


def get_local_cache_info():
    if not is_local_cache_available():
        return None
    import datetime
    mtime = datetime.datetime.fromtimestamp(LOCAL_CACHE_DB_PATH.stat().st_mtime)
    size = LOCAL_CACHE_DB_PATH.stat().st_size
    return {"built_at": mtime.isoformat(), "size_bytes": size}
