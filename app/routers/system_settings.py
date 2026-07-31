from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import require_admin, write_audit_log

router = APIRouter(prefix="/system-settings", tags=["系統設定（主題配色等全站設定）"])

AVAILABLE_THEMES = [
    {"id": "forest", "name": "森林綠（預設）"},
    {"id": "ocean", "name": "海洋藍"},
    {"id": "sunset", "name": "暖橘"},
    {"id": "slate", "name": "石墨灰"},
]
DEFAULT_THEME = "forest"


@router.get("/theme", summary="查詢目前系統配色主題（登入前後皆可查詢，不需權限）")
def get_theme(db: Session = Depends(get_db)):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "theme").first()
    return {"theme": setting.value if setting and setting.value else DEFAULT_THEME, "available": AVAILABLE_THEMES}


@router.put("/theme", summary="（後台）切換系統配色主題，全站套用")
def set_theme(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    theme_id = payload.get("theme")
    if theme_id not in [t["id"] for t in AVAILABLE_THEMES]:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="不是有效的主題名稱")
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "theme").first()
    if setting:
        setting.value = theme_id
    else:
        db.add(models.SystemSetting(key="theme", value=theme_id))
    db.commit()
    write_audit_log(db, admin, "update_theme", "system_setting", "theme", f"切換系統配色主題為 {theme_id}")
    return {"message": "已更新", "theme": theme_id}
