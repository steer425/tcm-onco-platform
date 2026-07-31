from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin

router = APIRouter(prefix="/login-logs", tags=["登入紀錄"])

# 登入紀錄僅供查詢與備注補充，不提供刪除（作為存取軌跡保留）。
# 備註：device_id 欄位為前端可選擇傳送的裝置識別資訊，
# 瀏覽器基於隱私限制無法取得真實網卡（MAC）位址，此為已知限制。


@router.get("", response_model=List[schemas.LoginLogOut], summary="查詢登入紀錄")
def list_login_logs(account: Optional[str] = None, db: Session = Depends(get_db),
                     admin: models.User = Depends(require_admin)):
    q = db.query(models.LoginLog)
    if account:
        q = q.filter(models.LoginLog.account.ilike(f"%{account}%"))
    return q.order_by(models.LoginLog.login_at.desc()).limit(500).all()


@router.put("/{log_id}/notes", response_model=schemas.LoginLogOut, summary="補充登入紀錄備注")
def update_notes(log_id: str, payload: schemas.LoginLogNoteUpdate, db: Session = Depends(get_db),
                  admin: models.User = Depends(require_admin)):
    log = db.query(models.LoginLog).filter(models.LoginLog.id == log_id).first()
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="找不到紀錄")
    log.notes = payload.notes
    db.commit()
    db.refresh(log)
    return log
