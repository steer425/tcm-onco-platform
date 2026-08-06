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


# ---------------------------------------------------------------------------
# 查詢站關聯網絡圖：每層節點顯示數量上限的「預設值」，三個查詢站（藥材/疾病/暗黑基因）共用同一組設定。
# 使用者在畫面上還是可以自行調整下拉選單，這裡只是決定「網頁一開始載入時」預設選中哪個數字，
# 不用像先前那樣寫死在前端程式碼裡（例如之前寫死「15」，改動還要重新部署前端）。
# ---------------------------------------------------------------------------

GRAPH_LIMIT_KEYS = {
    "graph_limit_level1": {"label": "網絡圖第一層節點數量上限（例如：每個藥材最多顯示幾個靶點）", "default": 8},
    "graph_limit_level2": {"label": "網絡圖第二層節點數量上限（例如：每個靶點最多顯示幾個成分/疾病）", "default": 5},
    "graph_limit_level3": {"label": "網絡圖第三層節點數量上限（例如：每個成分最多顯示幾種藥材）", "default": 15},
}


@router.get("/graph-limits", summary="查詢查詢站網絡圖節點數量上限的預設值（登入即可查詢）")
def get_graph_limits(db: Session = Depends(get_db)):
    result = {}
    for key, meta in GRAPH_LIMIT_KEYS.items():
        value = _get_setting_value(db, key)
        result[key] = int(value) if value else meta["default"]
    return result


@router.put("/graph-limits", summary="（後台）設定查詢站網絡圖節點數量上限的預設值")
def set_graph_limits(payload: dict, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    updated = {}
    for key in GRAPH_LIMIT_KEYS:
        if key in payload:
            value = int(payload[key])
            if value < 1 or value > 9999:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail=f"{key} 必須介於 1~9999 之間")
            _set_setting_value(db, key, value)
            updated[key] = value
    write_audit_log(db, admin, "update_graph_limits", "system_setting", "graph_limits", f"設定網絡圖節點數量上限預設值：{updated}")
    return {"message": "已更新", **updated}
