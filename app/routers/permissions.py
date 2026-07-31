from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin, write_audit_log

router = APIRouter(tags=["權限矩陣管理"])


# ---- Features (功能項目登錄) ----

@router.get("/features", response_model=List[schemas.FeatureOut], summary="查詢功能項目清單")
def list_features(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    return db.query(models.Feature).all()


@router.post("/features", response_model=schemas.FeatureOut, summary="新增功能項目")
def create_feature(payload: schemas.FeatureCreate, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    if db.query(models.Feature).filter(models.Feature.code == payload.code).first():
        raise HTTPException(status_code=400, detail="功能代碼已存在")
    feature = models.Feature(**payload.model_dump())
    db.add(feature)
    db.commit()
    db.refresh(feature)
    write_audit_log(db, admin, "create_feature", "feature", feature.id, f"新增功能項目 {feature.code}")
    return feature


@router.put("/features/{feature_id}", response_model=schemas.FeatureOut, summary="編輯功能項目（啟用/顯示前台/顯示後台/導覽文字/排序）")
def update_feature(feature_id: str, payload: schemas.FeatureUpdate, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    feature = db.query(models.Feature).filter(models.Feature.id == feature_id).first()
    if not feature:
        raise HTTPException(status_code=404, detail="找不到功能項目")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(feature, field, value)
    db.commit()
    db.refresh(feature)
    write_audit_log(db, admin, "update_feature", "feature", feature.id, f"編輯功能項目 {feature.code}")
    return feature


@router.delete("/features/{feature_id}", summary="刪除功能項目")
def delete_feature(feature_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    feature = db.query(models.Feature).filter(models.Feature.id == feature_id).first()
    if not feature:
        raise HTTPException(status_code=404, detail="找不到功能項目")
    db.delete(feature)
    db.commit()
    write_audit_log(db, admin, "delete_feature", "feature", feature_id, f"刪除功能項目 {feature.code}")
    return {"message": "已刪除"}


# ---- Role <-> Feature permission matrix ----

@router.get("/roles/{role_id}/permissions", response_model=List[schemas.RolePermissionOut],
            summary="查詢角色的權限矩陣")
def get_role_permissions(role_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="找不到角色")
    features = db.query(models.Feature).all()
    existing = {p.feature_id: p for p in role.permissions}
    result = []
    for f in features:
        p = existing.get(f.id)
        result.append(schemas.RolePermissionOut(
            feature_id=f.id, feature_code=f.code, feature_name=f.name,
            can_view=p.can_view if p else False,
            can_execute=p.can_execute if p else False,
            notes=p.notes if p else None,
        ))
    return result


@router.put("/roles/{role_id}/permissions", summary="設定（覆寫）角色的權限矩陣")
def set_role_permissions(role_id: str, payload: schemas.RolePermissionBulkUpdate,
                          db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="找不到角色")
    if role_id != payload.role_id:
        raise HTTPException(status_code=400, detail="role_id 不一致")

    for item in payload.permissions:
        perm = db.query(models.RolePermission).filter(
            models.RolePermission.role_id == role_id,
            models.RolePermission.feature_id == item.feature_id,
        ).first()
        if perm:
            perm.can_view = item.can_view
            perm.can_execute = item.can_execute
            perm.notes = item.notes
        else:
            db.add(models.RolePermission(
                role_id=role_id, feature_id=item.feature_id,
                can_view=item.can_view, can_execute=item.can_execute, notes=item.notes,
            ))
    db.commit()
    write_audit_log(db, admin, "update_role_permissions", "role", role_id,
                     f"更新角色 {role.name} 的權限矩陣（{len(payload.permissions)} 項）")
    return {"message": "權限矩陣已更新"}
