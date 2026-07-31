from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin, write_audit_log

router = APIRouter(prefix="/account-applications", tags=["帳號審核"])


@router.get("", response_model=List[schemas.ApplicationOut], summary="查詢帳號申請列表")
def list_applications(status_filter: Optional[str] = None, db: Session = Depends(get_db),
                       admin: models.User = Depends(require_admin)):
    q = db.query(models.AccountApplication)
    if status_filter:
        q = q.filter(models.AccountApplication.status == status_filter)
    return q.order_by(models.AccountApplication.created_at.desc()).all()


@router.put("/{application_id}/review", response_model=schemas.ApplicationOut, summary="審核帳號申請（通過/駁回）")
def review_application(application_id: str, payload: schemas.ApplicationReview,
                        db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    application = db.query(models.AccountApplication).filter(
        models.AccountApplication.id == application_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="找不到申請紀錄")
    if application.status != models.ApplicationStatus.pending:
        raise HTTPException(status_code=400, detail="此申請已審核過")

    application.status = models.ApplicationStatus.approved if payload.approve else models.ApplicationStatus.rejected
    application.reviewed_by = admin.id
    application.reviewed_at = datetime.utcnow()
    application.notes = payload.notes

    if application.user_id:
        user = db.query(models.User).filter(models.User.id == application.user_id).first()
        if user:
            if payload.approve:
                user.status = models.UserStatus.active
                default_role = db.query(models.Role).filter(models.Role.name == "一般使用者").first()
                if default_role and not user.roles:
                    db.add(models.UserRole(user_id=user.id, role_id=default_role.id))
            else:
                user.status = models.UserStatus.suspended
                user.suspend_reason = "帳號申請審核未通過"
    db.commit()
    db.refresh(application)
    write_audit_log(db, admin, "review_application", "account_application", application.id,
                     f"審核帳號申請 {application.account}: {'通過' if payload.approve else '駁回'}")
    return application


@router.delete("/{application_id}", summary="刪除申請紀錄")
def delete_application(application_id: str, db: Session = Depends(get_db),
                        admin: models.User = Depends(require_admin)):
    application = db.query(models.AccountApplication).filter(
        models.AccountApplication.id == application_id
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="找不到申請紀錄")
    db.delete(application)
    db.commit()
    write_audit_log(db, admin, "delete_application", "account_application", application_id, "刪除申請紀錄")
    return {"message": "已刪除"}
