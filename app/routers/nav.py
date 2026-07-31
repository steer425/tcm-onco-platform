from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import get_current_user, is_admin

router = APIRouter(prefix="/nav", tags=["導覽選單/功能顯示控制"])


@router.get("/menu", summary="取得目前使用者可見的功能項目（含頁面導覽與 Dashboard 小工具）")
def get_menu(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    features = (
        db.query(models.Feature)
        .filter(models.Feature.enabled == True)  # noqa: E712
        .order_by(models.Feature.sort_order)
        .all()
    )

    if is_admin(current_user):
        visible = features
    else:
        role_ids = [ur.role_id for ur in current_user.roles]
        if not role_ids:
            visible = []
        else:
            allowed_ids = {
                p.feature_id for p in db.query(models.RolePermission).filter(
                    models.RolePermission.role_id.in_(role_ids),
                    models.RolePermission.can_view == True,  # noqa: E712
                ).all()
            }
            visible = [f for f in features if f.id in allowed_ids]

    return [
        {
            "code": f.code,
            "nav_label": f.nav_label or f.name,
            "page_url": f.page_url,
            "show_frontend": f.show_frontend,
            "show_backend": f.show_backend,
            "module": f.module,
        }
        for f in visible
    ]
