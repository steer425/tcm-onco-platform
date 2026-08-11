import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 正式環境（Render 等）請設定環境變數 DATABASE_URL 指向雲端 PostgreSQL，
# 例如：postgresql://user:password@host:5432/dbname
# 本機開發若未設定 DATABASE_URL，則自動退回使用本機 SQLite 檔案，方便快速測試。
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./tcm_platform.db")

# Render / Heroku 等平台提供的連線字串常以 postgres:// 開頭，
# 但 SQLAlchemy 2.0 要求使用 postgresql://，這裡自動轉換以避免連線失敗。
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite 需要 check_same_thread=False 才能在 FastAPI 多執行緒環境下使用；PostgreSQL 不需要此設定。
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_query_db():
    """給查詢站關聯查詢用的 DB session。唯讀模式啟用且本機端快取存在時，
    直接讀本機端的 SQLite 快取檔案，不用連去遠端雲端資料庫，加快關聯查詢速度；
    其餘情況（唯讀模式關閉、或還沒建立過快取）就跟平常一樣連遠端資料庫，行為不變。"""
    db = SessionLocal()
    try:
        from app.routers.system_settings import _get_setting_value
        read_only = _get_setting_value(db, "read_only_mode") == "true"
        if read_only:
            from app.local_cache import get_local_cache_session, is_local_cache_available
            if is_local_cache_available():
                db.close()
                local_db = get_local_cache_session()
                try:
                    yield local_db
                finally:
                    local_db.close()
                return
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass
