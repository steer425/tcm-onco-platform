from fastapi import APIRouter, Depends

from app import models
from app.deps import get_current_user, get_user_role_names

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", summary="取得 Dashboard 內容（登入後可見，目前為施工中佔位頁）")
def get_dashboard(current_user: models.User = Depends(get_current_user)):
    return {
        "under_construction": True,
        "message": "Dashboard 施工中，敬請期待",
        "account": current_user.account,
        "role_names": get_user_role_names(current_user),
    }
