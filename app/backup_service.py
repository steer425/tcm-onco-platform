"""
資料庫備份服務：把整個資料庫內容匯出成一個加密檔案，供管理者從「系統設定」頁面下載到自己的電腦。

設計重點：
    - 路徑由系統自動決定（時間戳記命名），不開放使用者自訂路徑，存在專用的 backups/ 目錄
    - 備份檔案內容用 Fernet（對稱加密）加密後才寫入磁碟，即使檔案外流，沒有伺服器的密鑰也無法讀取內容
      （備份內容包含病患個資、DNA 資料、密碼雜湊等高度敏感資訊，這是刻意的安全設計，不是限制）
    - 加密金鑰衍生自 TCM_JWT_SECRET 環境變數（跟 JWT 簽章共用同一個密鑰來源，不需要額外設定新的環境變數）
    - 用 SQLAlchemy 的 metadata 動態列舉所有資料表，逐表匯出成 JSON，
      之後新增資料表不需要手動更新這支腳本
    - 這一版只做「匯出/下載」，還沒有做「還原」功能（還原會覆蓋現有資料，風險層級更高，
      建議之後如果要做，一定要有二次確認、且僅限最高權限管理者）
"""
import base64
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import text

from app import models
from app.security import SECRET_KEY

BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"


def _get_fernet_key() -> bytes:
    """從 TCM_JWT_SECRET 衍生出 Fernet 需要的 32 bytes urlsafe base64 金鑰，
    不用另外在環境變數裡設定第二把密鑰，減少部署時要記住的設定項目。"""
    digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()  # 32 bytes
    return base64.urlsafe_b64encode(digest)


def _serialize_row(row) -> dict:
    result = {}
    for col in row._mapping.keys():
        value = row._mapping[col]
        if isinstance(value, datetime):
            value = value.isoformat()
        result[col] = value
    return result


def dump_database_to_json(db) -> bytes:
    """用 SQLAlchemy metadata 動態列舉所有資料表，逐表把資料匯出成一份 JSON（未加密的原始內容）。"""
    dump = {
        "exported_at": datetime.utcnow().isoformat(),
        "tables": {},
    }
    for table in models.Base.metadata.sorted_tables:
        rows = db.execute(text(f'SELECT * FROM "{table.name}"')).fetchall()
        dump["tables"][table.name] = [_serialize_row(r) for r in rows]
    return json.dumps(dump, ensure_ascii=False, default=str).encode("utf-8")


def create_encrypted_backup(db) -> tuple:
    """建立一份加密備份檔案，回傳 (file_path, size_bytes)。路徑由系統自動決定，不開放使用者指定。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    plaintext = dump_database_to_json(db)
    fernet = Fernet(_get_fernet_key())
    encrypted = fernet.encrypt(plaintext)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.enc"
    file_path = BACKUP_DIR / filename

    with open(file_path, "wb") as f:
        f.write(encrypted)

    return str(file_path), len(encrypted)


def read_backup_file(file_path: str) -> bytes:
    """讀取加密備份檔案的原始位元組內容（維持加密狀態，不在這裡解密），供下載端點串流回傳。"""
    with open(file_path, "rb") as f:
        return f.read()
