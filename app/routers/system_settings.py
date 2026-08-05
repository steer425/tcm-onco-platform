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


# ---------------------------------------------------------------------------
# 查詢站預設項目：TCMSP 藥材/疾病查詢站首次載入時，只顯示這個預設項目，
# 減少一次載入全部資料造成的效能負擔（詳見 v1.16/v1.17 的漸進式載入設計）。
# ---------------------------------------------------------------------------

def _get_setting_value(db: Session, key: str):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    return setting.value if setting else None


def _set_setting_value(db: Session, key: str, value):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if setting:
        setting.value = str(value) if value is not None else None
    else:
        db.add(models.SystemSetting(key=key, value=str(value) if value is not None else None))
    db.commit()


@router.get("/default-herb", summary="查詢查詢站預設顯示的藥材（登入即可查詢）")
def get_default_herb(db: Session = Depends(get_db)):
    value = _get_setting_value(db, "default_herb_id")
    return {"herb_id": int(value) if value else None}


@router.put("/default-herb", summary="（後台）設定查詢站預設顯示的藥材")
def set_default_herb(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    herb_id = payload.get("herb_id")
    _set_setting_value(db, "default_herb_id", herb_id)
    write_audit_log(db, admin, "update_default_herb", "system_setting", "default_herb_id", f"設定預設藥材 herb_id={herb_id}")
    return {"message": "已更新", "herb_id": herb_id}


@router.get("/default-disease", summary="查詢查詢站預設顯示的疾病（登入即可查詢）")
def get_default_disease(db: Session = Depends(get_db)):
    value = _get_setting_value(db, "default_disease_id")
    return {"dis_id": value}


@router.put("/default-disease", summary="（後台）設定查詢站預設顯示的疾病")
def set_default_disease(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    dis_id = payload.get("dis_id")
    _set_setting_value(db, "default_disease_id", dis_id)
    write_audit_log(db, admin, "update_default_disease", "system_setting", "default_disease_id", f"設定預設疾病 dis_id={dis_id}")
    return {"message": "已更新", "dis_id": dis_id}
