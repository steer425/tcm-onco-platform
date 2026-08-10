from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/user-preferences", tags=["個人化設定（每位使用者各自的偏好設定）"])

# 目前支援的設定鍵值（供前台選單使用，之後有新的個人化設定項目可以繼續加）
ALLOWED_KEYS = {
    "query_station_theme": {"label": "關聯查詢站 CSS 設定", "options": ["dark", "light"], "default": "dark"},
    "site_language": {"label": "全站語系", "options": ["tw", "cn", "en", "ko"], "default": "tw"},
}


@router.get("/{key}", summary="查詢目前使用者的個人化設定值")
def get_preference(key: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    default = ALLOWED_KEYS.get(key, {}).get("default")
    pref = db.query(models.UserPreference).filter(
        models.UserPreference.user_id == current_user.id, models.UserPreference.key == key,
    ).first()
    return {"key": key, "value": pref.value if pref and pref.value else default}


@router.put("/{key}", summary="設定目前使用者的個人化設定值（只影響自己，不影響其他使用者）")
def set_preference(key: str, payload: dict, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    value = payload.get("value")
    allowed_options = ALLOWED_KEYS.get(key, {}).get("options")
    if allowed_options and value not in allowed_options:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"{key} 只能設定為以下其中之一：{', '.join(allowed_options)}")
    pref = db.query(models.UserPreference).filter(
        models.UserPreference.user_id == current_user.id, models.UserPreference.key == key,
    ).first()
    if pref:
        pref.value = value
    else:
        pref = models.UserPreference(user_id=current_user.id, key=key, value=value)
        db.add(pref)
    db.commit()
    return {"key": key, "value": value}
