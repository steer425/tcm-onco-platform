"""
Facebook OAuth 2.0 登入（Authorization Code Flow）

需要的環境變數（正式環境請於 Render 後台設定，不要寫死在程式碼或版本控制裡）：
- FACEBOOK_CLIENT_ID       Facebook App 的「應用程式編號」
- FACEBOOK_CLIENT_SECRET   Facebook App 的「應用程式密鑰」
- FACEBOOK_REDIRECT_URI    例如 https://tcm-onco-backend.onrender.com/auth/facebook/callback

申請方式見 README.md「Facebook OAuth 設定」章節。
"""
import os
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

FACEBOOK_CLIENT_ID = os.environ.get("FACEBOOK_CLIENT_ID", "")
FACEBOOK_CLIENT_SECRET = os.environ.get("FACEBOOK_CLIENT_SECRET", "")
FACEBOOK_REDIRECT_URI = os.environ.get("FACEBOOK_REDIRECT_URI", "http://localhost:8000/auth/facebook/callback")

FACEBOOK_API_VERSION = "v19.0"
FACEBOOK_AUTH_URL = f"https://www.facebook.com/{FACEBOOK_API_VERSION}/dialog/oauth"
FACEBOOK_TOKEN_URL = f"https://graph.facebook.com/{FACEBOOK_API_VERSION}/oauth/access_token"
FACEBOOK_USERINFO_URL = f"https://graph.facebook.com/{FACEBOOK_API_VERSION}/me"


def facebook_oauth_configured() -> bool:
    return bool(FACEBOOK_CLIENT_ID and FACEBOOK_CLIENT_SECRET)


def build_facebook_auth_url(state: str) -> str:
    if not facebook_oauth_configured():
        raise HTTPException(status_code=500, detail="尚未設定 FACEBOOK_CLIENT_ID / FACEBOOK_CLIENT_SECRET，Facebook 登入功能尚未啟用")
    params = {
        "client_id": FACEBOOK_CLIENT_ID,
        "redirect_uri": FACEBOOK_REDIRECT_URI,
        "response_type": "code",
        "scope": "email public_profile",
        "state": state,
    }
    return f"{FACEBOOK_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_userinfo(code: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.get(FACEBOOK_TOKEN_URL, params={
            "client_id": FACEBOOK_CLIENT_ID,
            "client_secret": FACEBOOK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": FACEBOOK_REDIRECT_URI,
        })
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Facebook token 交換失敗：{token_resp.text[:200]}")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Facebook 回應中沒有 access_token")

        userinfo_resp = await client.get(FACEBOOK_USERINFO_URL, params={
            "fields": "id,name,email",
            "access_token": access_token,
        })
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"取得 Facebook 使用者資訊失敗：{userinfo_resp.text[:200]}")
        return userinfo_resp.json()
