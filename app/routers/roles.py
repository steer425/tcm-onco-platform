from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin, write_audit_log

router = APIRouter(prefix="/roles", tags=["角色管理"])


def _to_out(role: models.Role) -> schemas.RoleOut:
    out = schemas.RoleOut.model_validate(role)
    out.user_count = len(role.users)
    return out


@router.get("", response_model=List[schemas.RoleOut], summary="查詢角色列表")
def list_roles(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    return [_to_out(r) for r in db.query(models.Role).all()]


@router.get("/{role_id}/users", response_model=List[schemas.UserOut], summary="查詢角色底下已設定帳號")
def list_role_users(role_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="找不到角色")
    from app.routers.users import _to_out as user_to_out
    return [user_to_out(ur.user) for ur in role.users]


@router.post("", response_model=schemas.RoleOut, summary="新增角色")
def create_role(payload: schemas.RoleCreate, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    if db.query(models.Role).filter(models.Role.name == payload.name).first():
        raise HTTPException(status_code=400, detail="角色名稱已存在")
    role = models.Role(name=payload.name, description=payload.description, notes=payload.notes)
    db.add(role)
    db.commit()
    db.refresh(role)
    write_audit_log(db, admin, "create_role", "role", role.id, f"新增角色 {role.name}")
    return _to_out(role)


@router.put("/{role_id}", response_model=schemas.RoleOut, summary="編輯角色")
def update_role(role_id: str, payload: schemas.RoleUpdate, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="找不到角色")
    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.notes is not None:
        role.notes = payload.notes
    db.commit()
    db.refresh(role)
    write_audit_log(db, admin, "update_role", "role", role.id, f"編輯角色 {role.name}")
    return _to_out(role)


@router.delete("/{role_id}", summary="刪除角色")
def delete_role(role_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="找不到角色")
    if role.is_system:
        raise HTTPException(status_code=400, detail="系統內建角色不可刪除")
    if role.users:
        raise HTTPException(status_code=400, detail="此角色底下仍有帳號，請先移除帳號的角色指派後再刪除")
    name = role.name
    db.delete(role)
    db.commit()
    write_audit_log(db, admin, "delete_role", "role", role_id, f"刪除角色 {name}")
    return {"message": "已刪除"}
