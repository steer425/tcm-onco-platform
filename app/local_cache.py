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
import json
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import DateTime, create_engine, text
from sqlalchemy.orm import sessionmaker

from app import models
from app.backup_service import _get_fernet_key

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
    """從最新一次成功備份的加密內容，重新建立本機端查詢快取。回傳寫入的資料列總數。"""
    if not latest_backup_job or not latest_backup_job.file_path:
        raise ValueError("找不到可用的備份紀錄，無法建立本機端快取")

    with open(latest_backup_job.file_path, "rb") as f:
        encrypted = f.read()
    fernet = Fernet(_get_fernet_key())
    dump = json.loads(fernet.decrypt(encrypted))
    tables_data = dump.get("tables", {})

    LOCAL_CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCAL_CACHE_DB_PATH.exists():
        LOCAL_CACHE_DB_PATH.unlink()  # 每次重建都整個重新來，避免舊資料殘留造成不一致

    global _local_engine, _LocalSessionLocal
    _local_engine = None  # 強制下次 _get_local_engine() 重新建立連線，指向剛清空重建的檔案
    engine = _get_local_engine()

    # 只在本機快取資料庫裡建立我們需要的那幾張表（用主資料庫的表結構定義），不用整份 schema
    tables_to_create = [t for t in models.Base.metadata.sorted_tables if t.name in CACHED_TABLES]
    models.Base.metadata.create_all(bind=engine, tables=tables_to_create)

    total_rows = 0
    with engine.begin() as conn:
        for table_name in CACHED_TABLES:
            rows = tables_data.get(table_name, [])
            if not rows:
                continue
            table_obj = next((t for t in tables_to_create if t.name == table_name), None)
            if table_obj is None:
                continue

            # 備份 JSON 裡的日期時間是用 .isoformat() 存成字串（app/backup_service.py 的 _serialize_row），
            # 但這裡要把資料寫回一個有正式 DateTime 欄位型別的資料表，SQLite 的 DateTime 型別只接受
            # 真正的 Python datetime 物件，不接受字串，插入前要轉換回來，不然會直接噴 TypeError。
            datetime_cols = [c.name for c in table_obj.columns if isinstance(c.type, DateTime)]
            if datetime_cols:
                for row in rows:
                    for col in datetime_cols:
                        val = row.get(col)
                        if isinstance(val, str) and val:
                            row[col] = datetime.datetime.fromisoformat(val)

            conn.execute(table_obj.insert(), rows)
            total_rows += len(rows)

    return total_rows


def get_local_cache_info():
    if not is_local_cache_available():
        return None
    import datetime
    mtime = datetime.datetime.fromtimestamp(LOCAL_CACHE_DB_PATH.stat().st_mtime)
    size = LOCAL_CACHE_DB_PATH.stat().st_size
    return {"built_at": mtime.isoformat(), "size_bytes": size}
