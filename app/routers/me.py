"""個人資訊（F0-18 個人化設定頁的「個人資訊」區塊）。

**一律只看得到、改得到自己。** 每個端點都只用 `get_current_user` 取出的那個人，
不接受任何 user_id 參數——要看別人的紀錄請走管理者的 `/login-logs`、`/audit-logs`。

  GET /me/profile       帳號、狀態、角色、第三方綁定、最近登入、最近一次自行變更密碼
  GET /me/login-logs    自己的登入紀錄
  GET /me/audit-logs    跟自己有關的異動紀錄：自己做的事 ＋ 別人對自己帳號做的事
  PUT /me/password      變更自己的密碼（要驗證目前密碼）

變更密碼列在唯讀模式的豁免清單（`main._READ_ONLY_EXEMPT_PATHS`）：
密碼外洩時要能立刻換，不能因為系統剛好在唯讀就卡住。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import get_current_user, write_audit_log
from app.security import hash_password, verify_password

router = APIRouter(prefix="/me", tags=["個人資訊（只限本人）"])

# 密碼規則與常見密碼清單移到 app/account_security.py（v1.49.0），所有設定密碼的地方共用一份
from app.account_security import PASSWORD_MAX_BYTES, PASSWORD_MIN, password_problem, revoke_all_sessions  # noqa: E402,F401
CHANGE_PASSWORD_ACTION = "change_own_password"
# 登入／登出在「登入紀錄」那一塊已經有了，異動紀錄預設不重複列
LOGIN_ACTIONS = ("login", "logout", "login_google", "login_facebook")

# 一眼就會被猜到的密碼。不求完整，只擋最常見的幾個，**尤其是種子帳號的預設值 0000**


def _iso(dt):
    return dt.isoformat() if dt else None


def _password_problem(new: str, account: str, current: str) -> str | None:
    return password_problem(new, account, current)


@router.get("/profile", summary="（本人）個人資訊摘要")
def my_profile(current_user: models.User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    u = current_user
    logs = (db.query(models.LoginLog).filter(models.LoginLog.user_id == u.id)
            .order_by(models.LoginLog.login_at.desc()).limit(2).all())
    n_logins = db.query(models.LoginLog).filter(models.LoginLog.user_id == u.id).count()
    pw = (db.query(models.AuditLog)
          .filter(models.AuditLog.actor_user_id == u.id,
                  models.AuditLog.action == CHANGE_PASSWORD_ACTION)
          .order_by(models.AuditLog.created_at.desc()).first())
    oauth = (db.query(models.OAuthAccount).filter(models.OAuthAccount.user_id == u.id)
             .order_by(models.OAuthAccount.linked_at).all())
    return {
        "account": u.account,
        "status": u.status.value if hasattr(u.status, "value") else u.status,
        "roles": [ur.role.name for ur in u.roles],
        "created_at": _iso(u.created_at),
        "updated_at": _iso(u.updated_at),
        "login_count": n_logins,
        # 第 0 筆通常就是「現在這一次」，上一次登入是第 1 筆
        "current_login_at": _iso(logs[0].login_at) if logs else None,
        "previous_login": ({"login_at": _iso(logs[1].login_at), "ip_address": logs[1].ip_address,
                            "user_agent": logs[1].user_agent} if len(logs) > 1 else None),
        "password_changed_at": _iso(pw.created_at) if pw else None,
        "oauth_accounts": [{"provider": o.provider.value if hasattr(o.provider, "value") else o.provider,
                            "linked_at": _iso(o.linked_at)} for o in oauth],
        "password_rules": {"min_length": PASSWORD_MIN, "max_bytes": PASSWORD_MAX_BYTES,
                           "need_letter_and_digit": True},
    }


@router.get("/login-logs", summary="（本人）登入紀錄")
def my_login_logs(limit: int = Query(50, ge=1, le=200),
                  current_user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    q = db.query(models.LoginLog).filter(models.LoginLog.user_id == current_user.id)
    total = q.count()
    rows = q.order_by(models.LoginLog.login_at.desc()).limit(limit).all()
    return {"total": total, "items": [{
        "id": r.id, "login_at": _iso(r.login_at), "logout_at": _iso(r.logout_at),
        "duration_seconds": r.duration_seconds, "ip_address": r.ip_address,
        "user_agent": r.user_agent,
        # 第三方登入的 user_agent 被寫成 "google-oauth"／"facebook-oauth"
        "method": ("google" if (r.user_agent or "").startswith("google-oauth")
                   else "facebook" if (r.user_agent or "").startswith("facebook-oauth")
                   else "password"),
    } for r in rows]}


@router.get("/audit-logs", summary="（本人）與自己帳號有關的異動紀錄")
def my_audit_logs(limit: int = Query(50, ge=1, le=200),
                  include_login: bool = Query(False, description="是否包含登入／登出（預設不含，登入紀錄另有一塊）"),
                  current_user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """兩種都列：**自己做的事**，以及**別人對自己帳號做的事**（例如管理者改了你的角色或重設密碼）。
    後者是這個區塊最重要的用途——帳號被動過，本人要看得到。"""
    A = models.AuditLog
    q = db.query(A).filter(or_(
        A.actor_user_id == current_user.id,
        and_(A.target_type == "user", A.target_id == current_user.id),
    ))
    if not include_login:
        q = q.filter(~A.action.in_(LOGIN_ACTIONS))
    total = q.count()
    rows = q.order_by(A.created_at.desc()).limit(limit).all()
    return {"total": total, "items": [{
        "id": r.id, "created_at": _iso(r.created_at), "action": r.action,
        "target_type": r.target_type, "detail": r.detail,
        "actor_account": r.actor_account or ("系統" if not r.actor_user_id else None),
        "by_me": r.actor_user_id == current_user.id,
    } for r in rows]}


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)
    confirm_password: str = Field(min_length=1, max_length=200)


@router.put("/password", summary="（本人）變更密碼")
def change_my_password(payload: PasswordChangeIn,
                       current_user: models.User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, current_user.password_hash):
        # 不寫稽核：這是輸入錯誤，不是異動；寫了反而會在異動紀錄裡留下一堆雜訊
        raise HTTPException(status_code=400, detail="目前密碼不正確")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="兩次輸入的新密碼不一致")
    problem = _password_problem(payload.new_password, current_user.account, payload.current_password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    current_user.password_hash = hash_password(payload.new_password)
    current_user.updated_at = datetime.utcnow()
    # v1.49.0：改密碼 = 所有裝置（含這一個）的登入全部失效。密碼外洩時，改完密碼對方手上的 token 也不能再用
    n = revoke_all_sessions(db, current_user)
    db.commit()
    # detail 只記事實，**絕不記任何密碼內容**
    write_audit_log(db, current_user, CHANGE_PASSWORD_ACTION, "user", current_user.id,
                    f"{current_user.account} 自行變更密碼（所有裝置登出，關閉 {n} 個登入）")
    return {"ok": True, "relogin": True,
            "message": "密碼已更新，所有裝置（包含這一個）都已登出，請用新密碼重新登入。"}


@router.post("/logout-all", summary="（本人）登出所有裝置：已發出的登入憑證全部失效")
def logout_all(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = revoke_all_sessions(db, current_user)
    db.commit()
    write_audit_log(db, current_user, "logout_all", "user", current_user.id,
                    f"{current_user.account} 登出所有裝置（關閉 {n} 個登入）")
    return {"ok": True, "relogin": True, "closed": n,
            "message": f"已登出所有裝置（{n} 個登入），請重新登入。"}
