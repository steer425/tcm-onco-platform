from sqlalchemy.orm import Session

from app import models
from app.feature_config import FEATURE_CONFIG
from app.security import hash_password

# 範例中藥行測試資料（僅供開發測試使用，正式資料請由後台管理頁面建置）
SAMPLE_PHARMACIES = [
    {"name": "仁和堂中藥行", "address": "台北市大同區迪化街一段 108 號",
     "phone": "02-2555-1234", "business_hours": "09:00-18:00（週日休）",
     "description": "百年老店，主營各式藥材批發與零售。", "latitude": "25.0574", "longitude": "121.5100"},
    {"name": "濟生堂國藥號", "address": "台北市大同區迪化街一段 71 號",
     "phone": "02-2555-5678", "business_hours": "09:30-18:30",
     "description": "提供中藥材諮詢與客製化藥膳包。", "latitude": "25.0561", "longitude": "121.5098"},
    {"name": "廣和堂藥行", "address": "新北市板橋區文化路一段 100 號",
     "phone": "02-2960-8888", "business_hours": "10:00-20:00",
     "description": "社區型中藥行，提供代客煎藥服務。", "latitude": "25.0100", "longitude": "121.4600"},
]


def seed_default_data(db: Session):
    # 系統內建角色
    if not db.query(models.Role).filter(models.Role.name == "管理者").first():
        db.add(models.Role(name="管理者", description="可查看並操作後台所有功能", is_system=True))
    if not db.query(models.Role).filter(models.Role.name == "一般使用者").first():
        db.add(models.Role(name="一般使用者", description="預設角色，僅能使用前台一般功能", is_system=True))
    db.commit()

    for item in FEATURE_CONFIG:
        if not db.query(models.Feature).filter(models.Feature.code == item["code"]).first():
            db.add(models.Feature(
                code=item["code"], module=item["module"], name=item["name"],
                nav_label=item.get("nav_label"), page_url=item.get("page_url"),
                show_frontend=item.get("show_frontend", False),
                show_backend=item.get("show_backend", True),
                sort_order=item.get("sort_order", 0),
                enabled=True,
            ))
    db.commit()

    # 預設「一般使用者」角色對所有前台功能給予可見權限（可事後於角色管理頁面調整）
    general_role = db.query(models.Role).filter(models.Role.name == "一般使用者").first()
    if general_role:
        for item in FEATURE_CONFIG:
            if not item.get("show_frontend"):
                continue
            feature = db.query(models.Feature).filter(models.Feature.code == item["code"]).first()
            if not feature:
                continue
            existing = db.query(models.RolePermission).filter(
                models.RolePermission.role_id == general_role.id,
                models.RolePermission.feature_id == feature.id,
            ).first()
            if not existing:
                db.add(models.RolePermission(role_id=general_role.id, feature_id=feature.id, can_view=True))
        db.commit()

    # 預設管理者帳號（僅限本機測試環境使用，正式環境請務必修改密碼）
    if not db.query(models.User).filter(models.User.account == "admin").first():
        admin_role = db.query(models.Role).filter(models.Role.name == "管理者").first()
        admin_user = models.User(
            account="admin",
            password_hash=hash_password("0000"),
            status=models.UserStatus.active,
            notes="系統預設管理者帳號，僅供本機測試，正式上線前請務必更改為高強度密碼",
        )
        db.add(admin_user)
        db.flush()
        db.add(models.UserRole(user_id=admin_user.id, role_id=admin_role.id))
        db.commit()

    # 範例中藥行測試資料（僅第一次啟動、資料表為空時建立）
    if db.query(models.Pharmacy).count() == 0:
        for item in SAMPLE_PHARMACIES:
            db.add(models.Pharmacy(**item, notes="系統範例測試資料"))
        db.commit()
