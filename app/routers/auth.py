import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, write_audit_log
from app.oauth_google import (
    FRONTEND_BASE_URL, build_google_auth_url, exchange_code_for_userinfo, google_oauth_configured,
)
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["登入與帳號申請"])

# 簡易 CSRF state 暫存：僅適合單一伺服器程序執行的情境。
# 若日後改用多 worker/多實例部署，需要改為 Redis 等跨程序共享的暫存機制。
_oauth_states: set = set()


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
    state = secrets.token_urlsafe(16)
    _oauth_states.add(state)
    return RedirectResponse(build_google_auth_url(state))


@router.get("/google/callback", summary="Google 登入回呼（由 Google 導回，不需前端直接呼叫）")
async def google_callback(code: str = None, state: str = None, error: str = None, db: Session = Depends(get_db)):
    def redirect_err(code_str: str):
        return RedirectResponse(f"{FRONTEND_BASE_URL}/oauth_callback.html?error={code_str}")

    if error:
        return redirect_err("google_denied")
    if not code or not state or state not in _oauth_states:
        return redirect_err("invalid_state")
    _oauth_states.discard(state)

    try:
        userinfo = await exchange_code_for_userinfo(code)
    except HTTPException:
        return redirect_err("token_exchange_failed")

    google_sub = userinfo.get("sub")
    email = userinfo.get("email")
    if not google_sub or not email:
        return redirect_err("missing_profile")

    link = db.query(models.OAuthAccount).filter(
        models.OAuthAccount.provider == models.OAuthProvider.google,
        models.OAuthAccount.provider_user_id == google_sub,
    ).first()

    if link:
        user = db.query(models.User).filter(models.User.id == link.user_id).first()
    else:
        user = db.query(models.User).filter(models.User.account == email).first()
        is_new_user = user is None
        if is_new_user:
            user = models.User(
                account=email,
                password_hash=hash_password(secrets.token_urlsafe(24)),  # 佔位密碼，使用者僅會透過 Google 登入
                status=models.UserStatus.pending,
                notes="透過 Google 登入自動建立帳號，待管理者審核",
            )
            db.add(user)
            db.flush()
            db.add(models.AccountApplication(account=email, user_id=user.id, notes="Google 第三方登入自動申請"))
        db.add(models.OAuthAccount(
            user_id=user.id, provider=models.OAuthProvider.google,
            provider_user_id=google_sub, notes=f"Google email: {email}",
        ))
        db.commit()
        db.refresh(user)
        write_audit_log(db, None, "google_oauth_link", "user", user.id, f"{email} 首次以 Google 登入並綁定帳號")

    if not user:
        return redirect_err("user_not_found")
    if user.status == models.UserStatus.pending:
        return redirect_err("pending_review")
    if user.status == models.UserStatus.suspended:
        return redirect_err("suspended")

    login_log = models.LoginLog(
        user_id=user.id, account=user.account, ip_address=None, user_agent="google-oauth",
    )
    db.add(login_log)
    db.commit()
    db.refresh(login_log)

    token = create_access_token({"sub": user.id, "acc": user.account})
    write_audit_log(db, user, "login_google", "user", user.id, f"{user.account} 以 Google 帳號登入")
    return RedirectResponse(f"{FRONTEND_BASE_URL}/oauth_callback.html?token={token}&login_log_id={login_log.id}")


@router.get("/me", response_model=schemas.UserOut, summary="取得目前登入者資訊")
def me(current_user: models.User = Depends(get_current_user)):
    result = schemas.UserOut.model_validate(current_user)
    result.role_names = [ur.role.name for ur in current_user.roles]
    return result
