import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.environ.get("TCM_JWT_SECRET", "dev-secret-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 小時

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def create_oauth_state_token() -> str:
    """產生第三方登入用的 CSRF state token：內容簽章 + 短效期（5 分鐘），
    驗證時不需要查伺服器端任何儲存狀態，因此不受「登入/回呼被導到不同伺服器程序」影響
    （例如 Render 重新部署交接期間，舊/新程序記憶體不共享的情境）。"""
    return jwt.encode(
        {"purpose": "oauth_state", "exp": datetime.utcnow() + timedelta(minutes=5)},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def verify_oauth_state_token(token: Optional[str]) -> bool:
    if not token:
        return False
    payload = decode_access_token(token)
    return bool(payload and payload.get("purpose") == "oauth_state")
