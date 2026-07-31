from sqlalchemy.orm import Session

from app import models
from app.security import hash_password

# 目標零功能清單登錄（對應 06_backend_crud_function_list.md）
DEFAULT_FEATURES = [
    ("F0-1", "目標零", "前後台架構"),
    ("F0-2", "目標零", "角色管理"),
    ("F0-3", "目標零", "後台登入權限控管"),
    ("F0-4", "目標零", "帳號申請審核"),
    ("F0-5", "目標零", "帳號停用啟用管理"),
    ("F0-6", "目標零", "第三方登入整合"),
    ("F0-7", "目標零", "資安規劃"),
    ("F0-8", "目標零", "報表設計"),
    ("F0-9", "目標零", "全站CRUD後台管理"),
    ("F0-10", "目標零", "資料庫備份與還原"),
    ("F0-11", "目標零", "稽核紀錄查詢"),
    ("F0-12", "目標零", "登入紀錄查詢"),
    ("F0-13", "目標零", "Dashboard"),
    ("F5-1", "目標五", "中藥行資料管理（後台）"),
    ("F5-2", "目標五", "中藥行地理推薦（前台）"),
    ("F5-3", "目標五", "評價管理（後台）"),
]

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

    for code, module, name in DEFAULT_FEATURES:
        if not db.query(models.Feature).filter(models.Feature.code == code).first():
            db.add(models.Feature(code=code, module=module, name=name))
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
