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
    {"name": "回春堂藥行", "address": "台北市大安區忠孝東路三段 55 號",
     "phone": "02-2771-3456", "business_hours": "09:00-19:00",
     "description": "老字號藥行，提供傳統方劑代客抓藥。", "latitude": "25.0418", "longitude": "121.5436"},
    {"name": "永和德安中藥房", "address": "新北市永和區永和路一段 20 號",
     "phone": "02-2921-7788", "business_hours": "09:30-20:30",
     "description": "社區藥房，主打養生藥膳茶飲配方。", "latitude": "25.0080", "longitude": "121.5150"},
    {"name": "松山長生堂", "address": "台北市松山區八德路四段 100 號",
     "phone": "02-2760-2345", "business_hours": "10:00-21:00",
     "description": "提供進口藥材與本土藥材雙線供應。", "latitude": "25.0500", "longitude": "121.5700"},
    {"name": "中和仁德藥行", "address": "新北市中和區中山路二段 200 號",
     "phone": "02-2246-9900", "business_hours": "09:00-18:30",
     "description": "配合鄰近中醫診所提供代煎服務。", "latitude": "24.9998", "longitude": "121.4990"},
    {"name": "新莊順天堂", "address": "新北市新莊區中正路 88 號",
     "phone": "02-2992-3344", "business_hours": "09:00-19:30",
     "description": "老牌藥行，兼營中藥材批發。", "latitude": "25.0360", "longitude": "121.4320"},
    {"name": "士林協和藥行", "address": "台北市士林區文林路 300 號",
     "phone": "02-2831-6688", "business_hours": "09:30-19:00",
     "description": "鄰近士林夜市，提供藥膳湯包配方諮詢。", "latitude": "25.0910", "longitude": "121.5250"},
    {"name": "內湖康寧藥行", "address": "台北市內湖區康寧路三段 50 號",
     "phone": "02-2632-7799", "business_hours": "10:00-20:00",
     "description": "提供客製化中藥調理諮詢服務。", "latitude": "25.0700", "longitude": "121.5900"},
    {"name": "桃園仁安堂", "address": "桃園市桃園區中正路 150 號",
     "phone": "03-332-5566", "business_hours": "09:00-18:00",
     "description": "桃園地區老字號中藥批發零售。", "latitude": "24.9930", "longitude": "121.3010"},
    {"name": "三重廣生堂", "address": "新北市三重區重新路三段 60 號",
     "phone": "02-2977-1122", "business_hours": "09:00-19:00",
     "description": "社區型中藥行，提供藥材代客研磨服務。", "latitude": "25.0630", "longitude": "121.4870"},
]


def seed_default_data(db: Session):
    # 系統內建角色
    if not db.query(models.Role).filter(models.Role.name == "管理者").first():
        db.add(models.Role(name="管理者", description="可查看並操作後台所有功能", is_system=True))
    if not db.query(models.Role).filter(models.Role.name == "一般使用者").first():
        db.add(models.Role(name="一般使用者", description="預設角色，僅能使用前台一般功能", is_system=True))
    db.commit()

    for item in FEATURE_CONFIG:
        existing = db.query(models.Feature).filter(models.Feature.code == item["code"]).first()
        if not existing:
            db.add(models.Feature(
                code=item["code"], module=item["module"], name=item["name"],
                nav_label=item.get("nav_label"), page_url=item.get("page_url"),
                show_frontend=item.get("show_frontend", False),
                show_backend=item.get("show_backend", True),
                sort_order=item.get("sort_order", 0),
                enabled=True,
            ))
        else:
            # 重要：既有功能項目的 module/name/nav_label/page_url/排序也要跟著更新，
            # 不能只在「代碼不存在」時才處理——不然像這次「F3-12 改名稱、改連結，但代碼沒變」
            # 這種情況，重啟伺服器（每次部署都會重啟）完全不會把新內容寫進資料庫，
            # 會卡在舊名稱/舊連結，兩個功能項目點進去變成同一個頁面，使用者以為是 bug，
            # 其實是資料庫沒有真的更新到——這是真實發生過的問題（v1.32.4）。
            # enabled／show_frontend／show_backend 這幾個「管理者可能已經在後台手動調整過」的欄位
            # 不在這裡覆蓋，避免蓋掉管理者的個別設定；只同步「開發者定義的內容性欄位」。
            existing.module = item["module"]
            existing.name = item["name"]
            existing.nav_label = item.get("nav_label")
            existing.page_url = item.get("page_url")
            existing.sort_order = item.get("sort_order", 0)
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

    # 範例中藥行測試資料：依名稱 upsert，已存在的不動，不存在的補上
    # （原本是「資料表為空才建立」，但正式環境已經有舊的 3 筆資料，改成 upsert 才能讓新增的樣本補進去，不會重複）
    existing_names = {p.name for p in db.query(models.Pharmacy.name).all()}
    for item in SAMPLE_PHARMACIES:
        if item["name"] not in existing_names:
            db.add(models.Pharmacy(**item, notes="系統範例測試資料"))
    db.commit()
