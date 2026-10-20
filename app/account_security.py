"""帳號安全的共用規則（v1.49.0）：帳號名稱格式、密碼規則、登入失敗鎖定、token 撤銷。

背景：2026-10-15 使用者電腦遭入侵（hosts 被竄改、10/19 仍在更新），這一版把平台本身的幾個缺口補上。
規則只寫在這裡一份，所有建立帳號／設定密碼／登入的路徑都呼叫這裡，不要各自重寫。

## token 撤銷

JWT 本身無法收回，所以 token 裡帶兩個識別：
  tv   使用者的 token_version。改密碼、管理者重設密碼或停用、「登出所有裝置」都會 +1，
       之前發出的 token 全部對不上 → 401。
  lid  這次登入的 LoginLog id。登出時寫入 logout_at，這個 token 就失效（只影響這一個裝置）。
沒有 tv／lid 的舊 token（v1.49.0 之前發的）視為 tv=0、不檢查 lid，上線當下不會把所有人踢出去；
最長 8 小時後自然過期。

## 欄位在啟動時自動補

`users.token_version / failed_login_count / locked_until` 每個需要登入的請求都會讀到。
依 rules.md 的慣例應該先手動跑 migrate_schema 再 push，但那要在本機輸入正式資料庫的連線字串——
在電腦還沒清乾淨的情況下，這等於把資料庫密碼交出去。所以這三個欄位由伺服器啟動時自己補（只加不改、
可重複執行），migrate_schema 也同步列入，兩邊都能補。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import inspect, text

from app import models
from app.security import create_access_token, hash_password, verify_password

# ---------------------------------------------------------------------------
# 帳號名稱
# ---------------------------------------------------------------------------
# 帳號名稱會顯示在管理者的審核頁與帳號列表。v1.49.0 以前沒有任何限制，又直接塞進 innerHTML——
# 匿名申請一個名稱帶 <img onerror=...> 的帳號，管理者打開審核頁就會執行（儲存型 XSS，可偷走管理者 token）。
# 前端已改成跳脫；這裡再從源頭只收安全字元。第三方登入用 email 當帳號，所以收 @ . + -。
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{2,63}$")


def account_problem(account: str | None) -> str | None:
    if not account or not ACCOUNT_RE.match(account):
        return "帳號只能使用英文字母、數字與 . _ @ + -，長度 3～64 字元，且第一個字必須是英文字母或數字"
    return None


# ---------------------------------------------------------------------------
# 密碼（v1.44.0 起用在「本人變更密碼」，v1.49.0 起所有設定密碼的地方都用）
# ---------------------------------------------------------------------------
PASSWORD_MIN = 8
PASSWORD_MAX_BYTES = 72   # bcrypt 只看前 72 個位元組；中文一個字 3 位元組，所以用位元組數判斷
COMMON_PASSWORDS = {
    "0000", "00000000", "12345678", "123456789", "1234567890", "password", "password1",
    "qwerty123", "11111111", "abc12345", "admin123", "admin1234", "iloveyou",
    "a1234567", "aa123456", "qwer1234", "1qaz2wsx", "p@ssw0rd", "passw0rd",
}


def password_problem(new: str, account: str | None = None, current: str | None = None) -> str | None:
    """回傳不合格的原因；合格回 None。規則刻意簡單、可以寫在畫面上讓人照著做。"""
    if not new or len(new) < PASSWORD_MIN:
        return f"密碼至少要 {PASSWORD_MIN} 個字元"
    if len(new.encode("utf-8")) > PASSWORD_MAX_BYTES:
        return f"密碼太長（超過 {PASSWORD_MAX_BYTES} 個位元組的部分不會生效）"
    if not any(c.isalpha() for c in new) or not any(c.isdigit() for c in new):
        return "密碼要同時包含英文字母與數字"
    if current is not None and new == current:
        return "新密碼不能與目前密碼相同"
    if account and account.lower() in new.lower():
        return "密碼不能包含帳號名稱"
    if new.lower() in COMMON_PASSWORDS:
        return "這個密碼太常見，請換一個"
    return None


# ---------------------------------------------------------------------------
# 登入失敗鎖定
# ---------------------------------------------------------------------------
MAX_FAILED = 5
LOCK_MINUTES = 15
_DUMMY_HASH: str | None = None


def burn_password_check(password: str) -> None:
    """帳號不存在時也跑一次 bcrypt，讓「帳號不存在」和「密碼錯」花的時間一樣，不能拿回應時間猜帳號。"""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("not-a-real-password-0")
    verify_password(password or "", _DUMMY_HASH)


def lock_remaining_minutes(user, now: datetime | None = None) -> int:
    """還鎖幾分鐘（無條件進位）；沒鎖回 0。"""
    now = now or datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        return max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
    return 0


def register_failure(user, now: datetime | None = None) -> bool:
    """記一次失敗；達上限就鎖住並歸零計數。回傳這次是否因此被鎖。"""
    now = now or datetime.utcnow()
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= MAX_FAILED:
        user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        user.failed_login_count = 0
        return True
    return False


def register_success(user) -> None:
    user.failed_login_count = 0
    user.locked_until = None


# ---------------------------------------------------------------------------
# token
# ---------------------------------------------------------------------------
def issue_token(user, login_log_id: str | None) -> str:
    data = {"sub": user.id, "acc": user.account, "tv": user.token_version or 0}
    if login_log_id:
        data["lid"] = login_log_id
    return create_access_token(data)


def revoke_all_sessions(db, user, now: datetime | None = None) -> int:
    """這個使用者已發出的 token 全部失效（token_version +1），並把還開著的登入紀錄標成登出。回傳關掉幾筆登入。"""
    now = now or datetime.utcnow()
    user.token_version = (user.token_version or 0) + 1
    open_logs = (db.query(models.LoginLog)
                 .filter(models.LoginLog.user_id == user.id, models.LoginLog.logout_at.is_(None)).all())
    for log in open_logs:
        log.logout_at = now
        if log.login_at:
            log.duration_seconds = int((now - log.login_at).total_seconds())
        log.notes = ((log.notes + "；") if log.notes else "") + "被撤銷（改密碼／停用／登出所有裝置）"
    return len(open_logs)


def token_problem(payload: dict, user, db) -> str | None:
    """token 是否已被撤銷；沒問題回 None。"""
    if (payload.get("tv") or 0) != (user.token_version or 0):
        return "登入已失效（密碼已變更、帳號狀態已調整或已登出所有裝置），請重新登入"
    lid = payload.get("lid")
    if lid:
        log = db.query(models.LoginLog).filter(models.LoginLog.id == lid).first()
        if log is None or log.user_id != user.id or log.logout_at is not None:
            return "這個登入已經登出，請重新登入"
    return None


# ---------------------------------------------------------------------------
# 啟動時補欄位
# ---------------------------------------------------------------------------
AUTH_COLUMNS = {
    "token_version": "INTEGER",
    "failed_login_count": "INTEGER",
    "locked_until": "TIMESTAMP",
}


def ensure_auth_columns(engine) -> list[str]:
    """users 少了哪個欄位就補哪個（只加、可重複執行）。回傳這次補了哪些。"""
    try:
        have = {c["name"] for c in inspect(engine).get_columns("users")}
    except Exception:  # noqa: BLE001 — 表還不存在（全新資料庫），create_all 會建
        return []
    added = []
    for name, typ in AUTH_COLUMNS.items():
        if name not in have:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {typ}"))
            added.append(name)
    return added
