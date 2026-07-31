from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin

router = APIRouter(prefix="/audit-logs", tags=["稽核紀錄"])

# 稽核紀錄僅提供「查詢」與「備注補充」，不提供刪除/修改，以保持軌跡完整性。


@router.get("", response_model=List[schemas.AuditLogOut], summary="查詢稽核紀錄")
def list_audit_logs(actor_account: Optional[str] = None, action: Optional[str] = None,
                     db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.AuditLog)
    if actor_account:
        q = q.filter(models.AuditLog.actor_account.ilike(f"%{actor_account}%"))
    if action:
        q = q.filter(models.AuditLog.action == action)
    return q.order_by(models.AuditLog.created_at.desc()).limit(500).all()


@router.put("/{log_id}/notes", response_model=schemas.AuditLogOut, summary="補充稽核紀錄備注")
def update_notes(log_id: str, payload: schemas.AuditLogNoteUpdate, db: Session = Depends(get_db),
                  admin: models.User = Depends(require_admin)):
    log = db.query(models.AuditLog).filter(models.AuditLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="找不到紀錄")
    log.notes = payload.notes
    db.commit()
    db.refresh(log)
    return log
