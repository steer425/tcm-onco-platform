from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import require_admin, write_audit_log

router = APIRouter(prefix="/backup-jobs", tags=["資料庫備份紀錄"])

# 說明：這裡先提供備份「紀錄」的查詢與手動登錄骨架。
# 實際自動排程備份（例如 cron + pg_dump/mysqldump 或雲端快照）需另外由維運端建置，
# 建置完成後在備份腳本結束時呼叫本 API 寫入結果即可串接。


@router.get("", response_model=List[schemas.BackupJobOut], summary="查詢備份紀錄")
def list_backup_jobs(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    return db.query(models.BackupJob).order_by(models.BackupJob.started_at.desc()).all()


@router.post("/trigger", response_model=schemas.BackupJobOut, summary="手動觸發一筆備份紀錄（骨架，尚未串接實際備份程序）")
def trigger_backup(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    job = models.BackupJob(status=models.BackupStatus.running, notes="手動觸發，待串接實際備份程序")
    db.add(job)
    db.commit()
    db.refresh(job)
    write_audit_log(db, admin, "trigger_backup", "backup_job", job.id, "手動觸發備份")
    return job


@router.put("/{job_id}/notes", response_model=schemas.BackupJobOut, summary="補充備份紀錄備注")
def update_notes(job_id: str, payload: schemas.BackupJobNoteUpdate, db: Session = Depends(get_db),
                  admin: models.User = Depends(require_admin)):
    job = db.query(models.BackupJob).filter(models.BackupJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="找不到備份紀錄")
    job.notes = payload.notes
    db.commit()
    db.refresh(job)
    return job


@router.delete("/{job_id}", summary="刪除備份紀錄（僅刪除紀錄本身，不影響實際備份檔案）")
def delete_job(job_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    job = db.query(models.BackupJob).filter(models.BackupJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="找不到備份紀錄")
    db.delete(job)
    db.commit()
    write_audit_log(db, admin, "delete_backup_job", "backup_job", job_id, "刪除備份紀錄")
    return {"message": "已刪除"}
