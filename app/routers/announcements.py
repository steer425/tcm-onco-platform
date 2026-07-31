import base64
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, require_admin, write_audit_log

router = APIRouter(prefix="/announcements", tags=["公告管理"])

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB，公告附件存資料庫（base64），避免單筆過大拖慢查詢


def _is_visible(a: models.Announcement, now: datetime) -> bool:
    if a.status != "active":
        return False
    if a.start_at and a.start_at > now:
        return False
    if a.end_at and a.end_at < now:
        return False
    return True


def _to_out(a: models.Announcement) -> schemas.AnnouncementOut:
    now = datetime.utcnow()
    out = schemas.AnnouncementOut.model_validate(a)
    out.is_currently_visible = _is_visible(a, now)
    return out


# ---------------------------------------------------------------------------
# 前台／一般登入使用者：只查目前應顯示的公告
# ---------------------------------------------------------------------------

@router.get("/public/active", response_model=List[schemas.AnnouncementOut], summary="（前台）查詢目前應顯示的公告")
def public_list_active(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    all_active_status = db.query(models.Announcement).filter(models.Announcement.status == "active").all()
    visible = [a for a in all_active_status if _is_visible(a, now)]
    visible.sort(key=lambda a: a.start_at, reverse=True)
    return [_to_out(a) for a in visible]


# ---------------------------------------------------------------------------
# 後台管理（僅限管理者）：完整 CRUD + 歷史查詢
# ---------------------------------------------------------------------------

@router.get("", response_model=List[schemas.AnnouncementOut], summary="（後台）查詢公告列表（含歷史/已過期，可查詢）")
def admin_list_announcements(keyword: Optional[str] = None, only_visible: Optional[bool] = None,
                              db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    q = db.query(models.Announcement)
    if keyword:
        q = q.filter(models.Announcement.title.ilike(f"%{keyword}%"))
    items = q.order_by(models.Announcement.start_at.desc()).all()
    results = [_to_out(a) for a in items]
    if only_visible is not None:
        results = [r for r in results if r.is_currently_visible == only_visible]
    return results


@router.post("", response_model=schemas.AnnouncementOut, summary="（後台）新增公告")
def admin_create_announcement(payload: schemas.AnnouncementCreate, db: Session = Depends(get_db),
                               admin: models.User = Depends(require_admin)):
    a = models.Announcement(
        title=payload.title, content=payload.content,
        start_at=payload.start_at, end_at=payload.end_at, notes=payload.notes,
        created_by=admin.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    write_audit_log(db, admin, "create_announcement", "announcement", a.id, f"新增公告《{a.title}》")
    return _to_out(a)


@router.put("/{announcement_id}", response_model=schemas.AnnouncementOut, summary="（後台）編輯公告")
def admin_update_announcement(announcement_id: str, payload: schemas.AnnouncementUpdate,
                               db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    a = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="找不到公告")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(a, field, value)
    db.commit()
    db.refresh(a)
    write_audit_log(db, admin, "update_announcement", "announcement", a.id, f"編輯公告《{a.title}》")
    return _to_out(a)


@router.delete("/{announcement_id}", summary="（後台）下架公告（軟刪除）")
def admin_delete_announcement(announcement_id: str, db: Session = Depends(get_db),
                               admin: models.User = Depends(require_admin)):
    a = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="找不到公告")
    a.status = "inactive"
    db.commit()
    write_audit_log(db, admin, "delete_announcement_soft", "announcement", a.id, f"下架公告《{a.title}》")
    return {"message": "已下架（軟刪除）"}


@router.post("/{announcement_id}/files", response_model=schemas.AnnouncementFileOut, summary="（後台）上傳公告附件")
async def admin_upload_file(announcement_id: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                             admin: models.User = Depends(require_admin)):
    a = db.query(models.Announcement).filter(models.Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="找不到公告")
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"檔案過大，上限 {MAX_FILE_SIZE // 1024 // 1024}MB")
    record = models.AnnouncementFile(
        announcement_id=announcement_id, filename=file.filename,
        content_type=file.content_type, file_size=len(content),
        file_data_base64=base64.b64encode(content).decode("ascii"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    write_audit_log(db, admin, "upload_announcement_file", "announcement", announcement_id,
                     f"上傳附件 {file.filename} 到公告《{a.title}》")
    return record


@router.delete("/files/{file_id}", summary="（後台）刪除公告附件")
def admin_delete_file(file_id: str, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    f = db.query(models.AnnouncementFile).filter(models.AnnouncementFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="找不到附件")
    db.delete(f)
    db.commit()
    write_audit_log(db, admin, "delete_announcement_file", "announcement_file", file_id, f"刪除附件 {f.filename}")
    return {"message": "已刪除"}


@router.get("/files/{file_id}/download", summary="下載公告附件（登入即可，前台/後台皆可用）")
def download_file(file_id: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = db.query(models.AnnouncementFile).filter(models.AnnouncementFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="找不到附件")
    content = base64.b64decode(f.file_data_base64)
    return Response(
        content=content,
        media_type=f.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{f.filename}"'},
    )
