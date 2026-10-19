"""
資料庫備份服務：把整個資料庫內容匯出成一個加密檔案，供管理者從「系統設定」頁面下載到自己的電腦。

設計重點：
    - 路徑由系統自動決定（時間戳記命名），不開放使用者自訂路徑，存在專用的 backups/ 目錄
    - 備份檔案內容用 Fernet（對稱加密）加密後才寫入磁碟，即使檔案外流，沒有伺服器的密鑰也無法讀取內容
      （備份內容包含病患個資、DNA 資料、密碼雜湊等高度敏感資訊，這是刻意的安全設計，不是限制）
    - 加密金鑰衍生自 TCM_JWT_SECRET 環境變數（跟 JWT 簽章共用同一個密鑰來源，不需要額外設定新的環境變數）
    - 用 SQLAlchemy 的 metadata 動態列舉所有資料表，逐表匯出，之後新增資料表不需要手動更新這支腳本
    - 還原見 app/backup_restore.py（v1.48.2）：只還原到空的資料庫，不覆蓋現有資料。
      （就地覆蓋正式庫的風險太高，刻意不做）

## v1.48.3：分段串流（格式 2）

舊寫法（格式 1）把整個資料庫一次讀進記憶體、整份轉成 JSON、再整份加密——同一份資料同時在記憶體裡
放三、四份。DepMap 細胞株依賴匯入後資料量變大，實測 40 萬列時峰值 546 MB，超過 Render 免費方案的
512 MB，伺服器在備份途中被強制重啟：前端輪詢看到「無法連線到伺服器」，背景工作跟著消失，
那筆紀錄永遠停在「進行中」（10/18 實際發生）。

格式 2 逐表、每 `CHUNK_ROWS` 列一段：JSON → gzip → Fernet，一段一行寫進檔案。記憶體只放一段，
與資料庫大小無關。檔案結尾一段是 meta（各表筆數），還原時拿來核對檔案有沒有被截斷。
先寫到 `.partial`，全部寫完才改名——寫到一半掛掉的檔案不會被當成完整備份。

    第 1 行   TCMBAK2
    之後每行  Fernet(gzip(JSON {"t": 表名, "r": [列...]}))
    最後一行  Fernet(gzip(JSON {"meta": {"format": 2, "exported_at": ..., "counts": {表: 筆數}}}))
"""
import base64
import gzip
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
MAGIC = b"TCMBAK2\n"
CHUNK_ROWS = 2000


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


def _seal(fernet: Fernet, obj) -> bytes:
    raw = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    return fernet.encrypt(gzip.compress(raw, compresslevel=6)) + b"\n"


def write_backup_stream(db, out, chunk_rows: int = CHUNK_ROWS) -> dict:
    """把整個資料庫以格式 2 寫進 out（binary file）。回傳 {表: 筆數}。

    逐表用 stream_results 分批讀，PostgreSQL 會用伺服器端游標，不會一次把整張表拉進記憶體。
    """
    fernet = Fernet(_get_fernet_key())
    out.write(MAGIC)
    counts = {}
    conn = db.connection().execution_options(stream_results=True, yield_per=chunk_rows)
    for table in models.Base.metadata.sorted_tables:
        n = 0
        result = conn.execute(text(f'SELECT * FROM "{table.name}"'))
        for part in result.partitions(chunk_rows):
            rows = [_serialize_row(r) for r in part]
            out.write(_seal(fernet, {"t": table.name, "r": rows}))
            n += len(rows)
        if n == 0:
            out.write(_seal(fernet, {"t": table.name, "r": []}))   # 讓還原端知道這張表存在、只是空的
        counts[table.name] = n
    out.write(_seal(fernet, {"meta": {"format": 2, "exported_at": datetime.utcnow().isoformat(),
                                      "counts": counts}}))
    return counts


def create_encrypted_backup(db) -> tuple:
    """建立一份加密備份檔案，回傳 (file_path, size_bytes)。路徑由系統自動決定，不開放使用者指定。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_path = BACKUP_DIR / f"backup_{timestamp}.enc"
    partial = file_path.with_suffix(".enc.partial")
    try:
        with open(partial, "wb") as f:
            write_backup_stream(db, f)
        os.replace(partial, file_path)
    finally:
        if partial.exists():
            partial.unlink()
    return str(file_path), file_path.stat().st_size


def mark_interrupted_backups(db) -> int:
    """啟動時呼叫：把還停在 running 的備份紀錄改成 failed。

    備份是同一個行程裡的背景工作；行程一重啟（部署、休眠喚醒、記憶體不足被砍），工作就沒了，
    不會有人回頭改狀態，紀錄會永遠顯示「進行中」。Render 上只有一個 uvicorn 行程，
    所以啟動當下還是 running 的，一定是上一個行程留下的。
    """
    stuck = db.query(models.BackupJob).filter(models.BackupJob.status == models.BackupStatus.running).all()
    for job in stuck:
        job.status = models.BackupStatus.failed
        job.finished_at = datetime.utcnow()
        job.notes = ("沒有完成：伺服器在備份過程中重新啟動（部署、休眠喚醒或記憶體不足），背景工作被中斷。"
                     "請重新建立一次備份。")
    if stuck:
        db.commit()
    return len(stuck)


def read_backup_file(file_path: str) -> bytes:
    """讀取加密備份檔案的原始位元組內容（維持加密狀態，不在這裡解密），供下載端點串流回傳。"""
    with open(file_path, "rb") as f:
        return f.read()
