from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="無法驗證身分，請重新登入",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    payload = decode_access_token(token)
    if not payload:
        raise credentials_exception
    user_id = payload.get("sub")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise credentials_exception
    if user.status != models.UserStatus.active:
        raise HTTPException(status_code=403, detail="帳號未啟用或已被停用")
    return user


def get_user_role_names(user: models.User) -> list:
    return [ur.role.name for ur in user.roles]


def is_admin(user: models.User) -> bool:
    return "管理者" in get_user_role_names(user)


def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="需要管理者權限")
    return current_user


def require_permission(feature_code: str, need_execute: bool = True):
    """依角色權限矩陣檢查目前使用者是否可執行(或可見)指定功能"""

    def checker(
        current_user: models.User = Depends(get_current_user),
        db: "Session" = Depends(get_db),
    ) -> models.User:
        if is_admin(current_user):
            return current_user
        role_ids = [ur.role_id for ur in current_user.roles]
        if not role_ids:
            raise HTTPException(status_code=403, detail="尚未指派角色，無法使用此功能")
        feature = db.query(models.Feature).filter(models.Feature.code == feature_code).first()
        if not feature:
            raise HTTPException(status_code=500, detail=f"功能代碼 {feature_code} 尚未於系統登錄")
        perm = (
            db.query(models.RolePermission)
            .filter(
                models.RolePermission.role_id.in_(role_ids),
                models.RolePermission.feature_id == feature.id,
            )
            .all()
        )
        allowed = any((p.can_execute if need_execute else p.can_view) for p in perm)
        if not allowed:
            raise HTTPException(status_code=403, detail="您的角色沒有此功能的操作權限")
        return current_user

    return checker


def has_permission(db: "Session", user: models.User, feature_code: str, need_execute: bool = False) -> bool:
    """`require_permission()` 的非阻斷版本：回傳布林值而不是拋例外，
    供「依權限調整回傳內容/篩選條件」而不是「整支端點擋掉」的情境使用
    （例如新聞未解禁內容：一般使用者看不到，不代表整支 API 要 403）。"""
    if is_admin(user):
        return True
    role_ids = [ur.role_id for ur in user.roles]
    if not role_ids:
        return False
    feature = db.query(models.Feature).filter(models.Feature.code == feature_code).first()
    if not feature:
        return False
    perm = (
        db.query(models.RolePermission)
        .filter(
            models.RolePermission.role_id.in_(role_ids),
            models.RolePermission.feature_id == feature.id,
        )
        .all()
    )
    return any((p.can_execute if need_execute else p.can_view) for p in perm)


def write_audit_log(db: "Session", actor: Optional[models.User], action: str,
                     target_type: str = None, target_id: str = None, detail: str = None):
    log = models.AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_account=actor.account if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    db.add(log)
    db.commit()
