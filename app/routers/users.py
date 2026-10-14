from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin, write_audit_log
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["帳號管理"])


def _to_out(user: models.User) -> schemas.UserOut:
    out = schemas.UserOut.model_validate(user)
    out.role_names = [ur.role.name for ur in user.roles]
    return out


@router.get("", response_model=List[schemas.UserOut], summary="查詢帳號列表")
def list_users(keyword: Optional[str] = None, status_filter: Optional[str] = None,
               db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.User)
    if keyword:
        q = q.filter(models.User.account.ilike(f"%{keyword}%"))
    if status_filter:
        q = q.filter(models.User.status == status_filter)
    return [_to_out(u) for u in q.order_by(models.User.created_at.desc()).all()]


@router.post("", response_model=schemas.UserOut, summary="新增帳號（管理者直接建立，略過審核）")
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    if db.query(models.User).filter(models.User.account == payload.account).first():
        raise HTTPException(status_code=400, detail="帳號已存在")
    user = models.User(
        account=payload.account,
        password_hash=hash_password(payload.password),
        status=models.UserStatus.active,
        notes=payload.notes,
    )
    db.add(user)
    db.flush()
    for rid in payload.role_ids:
        db.add(models.UserRole(user_id=user.id, role_id=rid))
    db.commit()
    db.refresh(user)
    write_audit_log(db, admin, "create_user", "user", user.id, f"管理者建立帳號 {user.account}")
    return _to_out(user)


@router.put("/{user_id}", response_model=schemas.UserOut, summary="修改帳號（狀態/停用原因/備注/角色/密碼）")
def update_user(user_id: str, payload: schemas.UserUpdate, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到帳號")
    # 記下這次改了哪些欄位：本人會在「個人化設定 → 異動紀錄」看到這一筆（v1.44.0），
    # 只寫「更新帳號」的話，被重設密碼或被改角色的人看不出發生了什麼。**密碼內容絕不寫入。**
    changed = []
    if payload.status is not None:
        if user.status != payload.status:
            changed.append(f"狀態 → {payload.status.value if hasattr(payload.status, 'value') else payload.status}")
        user.status = payload.status
    if payload.suspend_reason is not None:
        user.suspend_reason = payload.suspend_reason
    if payload.notes is not None:
        user.notes = payload.notes
    if payload.password:
        user.password_hash = hash_password(payload.password)
        changed.append("重設密碼")
    if payload.role_ids is not None:
        changed.append("調整角色")
        db.query(models.UserRole).filter(models.UserRole.user_id == user.id).delete()
        for rid in payload.role_ids:
            db.add(models.UserRole(user_id=user.id, role_id=rid))
    db.commit()
    db.refresh(user)
    write_audit_log(db, admin, "update_user", "user", user.id,
                    f"更新帳號 {user.account}" + (f"（{'、'.join(changed)}）" if changed else ""))
    return _to_out(user)


@router.delete("/{user_id}", summary="刪除帳號（採軟刪除：標記為停用）")
def delete_user(user_id: str, reason: Optional[str] = "後台刪除", db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到帳號")
    user.status = models.UserStatus.suspended
    user.suspend_reason = reason
    db.commit()
    write_audit_log(db, admin, "delete_user_soft", "user", user.id, f"軟刪除帳號 {user.account}: {reason}")
    return {"message": "已停用（軟刪除）"}
