import asyncio
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, write_audit_log
from app.oauth_facebook import (
    build_facebook_auth_url, exchange_code_for_userinfo as facebook_exchange_code_for_userinfo,
    facebook_oauth_configured,
)
from app.oauth_google import (
    FRONTEND_BASE_URL, build_google_auth_url, exchange_code_for_userinfo as google_exchange_code_for_userinfo,
    google_oauth_configured,
)
from app.security import create_access_token, create_oauth_state_token, hash_password, verify_oauth_state_token, verify_password

router = APIRouter(prefix="/auth", tags=["登入與帳號申請"])

# 部分瀏覽器/Facebook 登入完成頁會觸發兩次跳轉到 callback 網址（同一組授權碼送兩次），
# 而且兩次幾乎是同時發生的——單純檢查「有沒有快取結果」擋不住這種併發情境：
# 兩個請求都在對方還沒寫入快取之前，就各自檢查到「快取是空的」，於是雙雙跑去跟 Facebook/Google 交換，
# 其中一個一定會撞到「授權碼已使用過」的錯誤。
# 解法：用同一組授權碼的 asyncio.Lock 讓第二個請求「排隊等待」第一個請求做完，
# 而不是兩個同時衝去對第三方發請求。第一個請求做完後，第二個請求拿鎖時直接讀到快取結果，
# 不會再重新呼叫第三方 API。
_recent_oauth_redirects: dict = {}
_oauth_code_locks: dict = {}
_oauth_lock_registry_guard = asyncio.Lock()  # 保護 _oauth_code_locks 這個 dict 本身的建立過程
_OAUTH_REPLAY_CACHE_SECONDS = 60


async def _get_oauth_code_lock(code: str) -> asyncio.Lock:
    async with _oauth_lock_registry_guard:
        if code not in _oauth_code_locks:
            _oauth_code_locks[code] = asyncio.Lock()
        return _oauth_code_locks[code]


def _cache_oauth_result(code: str, response: RedirectResponse):
    now = datetime.utcnow().timestamp()
    # 順手清掉過期的快取項目，避免無限增長
    for k in list(_recent_oauth_redirects.keys()):
        if now - _recent_oauth_redirects[k][1] > _OAUTH_REPLAY_CACHE_SECONDS:
            del _recent_oauth_redirects[k]
    _recent_oauth_redirects[code] = (response, now)


def _get_cached_oauth_result(code: str) -> Optional[RedirectResponse]:
    entry = _recent_oauth_redirects.get(code)
    if not entry:
        return None
    response, ts = entry
    if datetime.utcnow().timestamp() - ts > _OAUTH_REPLAY_CACHE_SECONDS:
        return None
    return response


def _redirect_oauth_error(code_str: str) -> RedirectResponse:
    return RedirectResponse(f"{FRONTEND_BASE_URL}/oauth_callback.html?error={code_str}")


def _handle_oauth_login(db: Session, provider: models.OAuthProvider, provider_user_id: str,
                         email: str, provider_label: str) -> RedirectResponse:
    """Google／Facebook 共用的帳號綁定與登入邏輯：
    - 已綁定過 → 直接登入該帳號
    - 沒綁定過但 email 對應到既有帳號 → 自動綁定該帳號（第三方已驗證 email 擁有權，視為可信）
    - 都沒有 → 建立新帳號（狀態：審核中），走跟一般註冊一樣的帳號審核流程
    """
    link = db.query(models.OAuthAccount).filter(
        models.OAuthAccount.provider == provider,
        models.OAuthAccount.provider_user_id == provider_user_id,
    ).first()

    if link:
        user = db.query(models.User).filter(models.User.id == link.user_id).first()
    else:
        user = db.query(models.User).filter(models.User.account == email).first()
        is_new_user = user is None
        if is_new_user:
            user = models.User(
                account=email,
                password_hash=hash_password(secrets.token_urlsafe(24)),  # 佔位密碼，使用者僅會透過第三方登入
                status=models.UserStatus.pending,
                notes=f"透過 {provider_label} 登入自動建立帳號，待管理者審核",
            )
            db.add(user)
            db.flush()
            db.add(models.AccountApplication(account=email, user_id=user.id, notes=f"{provider_label} 第三方登入自動申請"))
        db.add(models.OAuthAccount(
            user_id=user.id, provider=provider,
            provider_user_id=provider_user_id, notes=f"{provider_label} email: {email}",
        ))
        db.commit()
        db.refresh(user)
        write_audit_log(db, None, f"{provider.value}_oauth_link", "user", user.id,
                         f"{email} 首次以 {provider_label} 登入並綁定帳號")

    if not user:
        return _redirect_oauth_error("user_not_found")
    if user.status == models.UserStatus.pending:
        return _redirect_oauth_error("pending_review")
    if user.status == models.UserStatus.suspended:
        return _redirect_oauth_error("suspended")

    login_log = models.LoginLog(
        user_id=user.id, account=user.account, ip_address=None, user_agent=f"{provider.value}-oauth",
    )
    db.add(login_log)
    db.commit()
    db.refresh(login_log)

    token = create_access_token({"sub": user.id, "acc": user.account})
    write_audit_log(db, user, f"login_{provider.value}", "user", user.id, f"{user.account} 以 {provider_label} 帳號登入")
    return RedirectResponse(f"{FRONTEND_BASE_URL}/oauth_callback.html?token={token}&login_log_id={login_log.id}")


@router.post("/apply", response_model=schemas.ApplicationOut, summary="申請新帳號")
def apply_account(payload: schemas.ApplyAccountRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.account == payload.account).first()
    if existing:
        raise HTTPException(status_code=400, detail="此帳號已存在或已提出申請")

    user = models.User(
        account=payload.account,
        password_hash=hash_password(payload.password),
        status=models.UserStatus.pending,
        notes=payload.notes,
    )
    db.add(user)
    db.flush()

    application = models.AccountApplication(account=payload.account, user_id=user.id, notes=payload.notes)
    db.add(application)
    db.commit()
    db.refresh(application)
    write_audit_log(db, None, "apply_account", "user", user.id, f"帳號 {payload.account} 提出申請")
    return application


@router.post("/login", response_model=schemas.TokenResponse, summary="登入")
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.account == payload.account).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    if user.status == models.UserStatus.pending:
        raise HTTPException(status_code=403, detail="帳號審核中，請等待管理者審核通過")
    if user.status == models.UserStatus.suspended:
        raise HTTPException(status_code=403, detail=f"帳號已停用：{user.suspend_reason or '未填寫原因'}")

    client_ip = request.client.host if request.client else None
    login_log = models.LoginLog(
        user_id=user.id,
        account=user.account,
        ip_address=client_ip,
        device_id=payload.device_id,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(login_log)
    db.commit()
    db.refresh(login_log)

    token = create_access_token({"sub": user.id, "acc": user.account})
    write_audit_log(db, user, "login", "user", user.id, f"{user.account} 登入系統")
    return schemas.TokenResponse(access_token=token, login_log_id=login_log.id)


@router.post("/logout", summary="登出")
def logout(login_log_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    log = db.query(models.LoginLog).filter(
        models.LoginLog.id == login_log_id, models.LoginLog.user_id == current_user.id
    ).first()
    if not log:
        raise HTTPException(status_code=404, detail="找不到對應的登入紀錄")
    log.logout_at = datetime.utcnow()
    log.duration_seconds = int((log.logout_at - log.login_at).total_seconds())
    db.commit()
    write_audit_log(db, current_user, "logout", "user", current_user.id, f"{current_user.account} 登出系統")
    return {"message": "已登出", "duration_seconds": log.duration_seconds}


@router.get("/google/enabled", summary="查詢 Google 登入是否已啟用（供前台判斷是否顯示按鈕）")
def google_enabled():
    return {"enabled": google_oauth_configured()}


@router.get("/google/login", summary="導向 Google 登入頁")
def google_login():
    state = create_oauth_state_token()
    return RedirectResponse(build_google_auth_url(state))


@router.get("/google/callback", summary="Google 登入回呼（由 Google 導回，不需前端直接呼叫）")
async def google_callback(code: str = None, state: str = None, error: str = None, db: Session = Depends(get_db)):
    if error:
        return _redirect_oauth_error("google_denied")
    if not verify_oauth_state_token(state):
        return _redirect_oauth_error("invalid_state")
    if not code:
        return _redirect_oauth_error("missing_code")

    lock = await _get_oauth_code_lock(code)
    async with lock:
        cached = _get_cached_oauth_result(code)
        if cached:
            return cached

        try:
            userinfo = await google_exchange_code_for_userinfo(code)
        except HTTPException as e:
            print(f"[Google OAuth] token exchange failed: {e.detail}")
            return _redirect_oauth_error("token_exchange_failed")

        google_sub = userinfo.get("sub")
        email = userinfo.get("email")
        if not google_sub or not email:
            return _redirect_oauth_error("missing_profile")

        result = _handle_oauth_login(db, models.OAuthProvider.google, google_sub, email, "Google")
        _cache_oauth_result(code, result)
        return result


@router.get("/facebook/enabled", summary="查詢 Facebook 登入是否已啟用（供前台判斷是否顯示按鈕）")
def facebook_enabled():
    return {"enabled": facebook_oauth_configured()}


@router.get("/facebook/login", summary="導向 Facebook 登入頁")
def facebook_login():
    state = create_oauth_state_token()
    return RedirectResponse(build_facebook_auth_url(state))


@router.get("/facebook/callback", summary="Facebook 登入回呼（由 Facebook 導回，不需前端直接呼叫）")
async def facebook_callback(code: str = None, state: str = None, error: str = None, db: Session = Depends(get_db)):
    if error:
        return _redirect_oauth_error("facebook_denied")
    if not verify_oauth_state_token(state):
        return _redirect_oauth_error("invalid_state")
    if not code:
        return _redirect_oauth_error("missing_code")

    lock = await _get_oauth_code_lock(code)
    async with lock:
        cached = _get_cached_oauth_result(code)
        if cached:
            return cached

        try:
            userinfo = await facebook_exchange_code_for_userinfo(code)
        except HTTPException as e:
            print(f"[Facebook OAuth] token exchange failed: {e.detail}")
            return _redirect_oauth_error("token_exchange_failed")

        facebook_id = userinfo.get("id")
        email = userinfo.get("email")
        if not facebook_id:
            return _redirect_oauth_error("missing_profile")
        if not email:
            # 部分 Facebook 帳號沒有綁定 email（例如手機號碼註冊），這裡直接擋下並提示，
            # 因為本系統的帳號體系以 email 作為帳號識別，無法用純數字 ID 建立有意義的帳號名稱。
            return _redirect_oauth_error("facebook_no_email")

        result = _handle_oauth_login(db, models.OAuthProvider.facebook, facebook_id, email, "Facebook")
        _cache_oauth_result(code, result)
        return result


@router.get("/me", response_model=schemas.UserOut, summary="取得目前登入者資訊")
def me(current_user: models.User = Depends(get_current_user)):
    result = schemas.UserOut.model_validate(current_user)
    result.role_names = [ur.role.name for ur in current_user.roles]
    return result
