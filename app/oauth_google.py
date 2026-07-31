"""
Google OAuth 2.0 登入（Authorization Code Flow）

需要的環境變數（正式環境請於 Render 後台設定，不要寫死在程式碼或版本控制裡）：
- GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_SECRET
- GOOGLE_REDIRECT_URI  例如 https://tcm-onco-backend.onrender.com/auth/google/callback
- FRONTEND_BASE_URL    例如 https://fwc-tcmsp.pages.dev（不含結尾斜線）

申請方式見 docs/README.md「Google OAuth 設定」章節。
"""
import os
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:8000/app").rstrip("/")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def google_oauth_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def build_google_auth_url(state: str) -> str:
    if not google_oauth_configured():
        raise HTTPException(status_code=500, detail="尚未設定 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET，Google 登入功能尚未啟用")
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_userinfo(code: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI,
        })
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Google token 交換失敗：{token_resp.text[:200]}")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Google 回應中沒有 access_token")

        userinfo_resp = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"取得 Google 使用者資訊失敗：{userinfo_resp.text[:200]}")
        return userinfo_resp.json()
