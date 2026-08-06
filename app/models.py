import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_id():
    return str(uuid.uuid4())


class UserStatus(str, enum.Enum):
    pending = "pending"       # 審核中
    active = "active"         # 啟用
    suspended = "suspended"   # 停用中


class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class OAuthProvider(str, enum.Enum):
    google = "google"
    facebook = "facebook"
    xiaohongshu = "xiaohongshu"
    wechat = "wechat"


class BackupStatus(str, enum.Enum):
    success = "success"
    failed = "failed"
    running = "running"


# ---------- 目標零：帳號 / 角色 / 權限 ----------

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    account = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    status = Column(Enum(UserStatus), default=UserStatus.pending, nullable=False)
    suspend_reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    is_system = Column(Boolean, default=False)  # 系統內建角色（如一般使用者/管理者）不可刪除
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role_id = Column(String, ForeignKey("roles.id"), nullable=False)

    user = relationship("User", back_populates="roles")
    role = relationship("Role", back_populates="users")


class Feature(Base):
    """對應各功能模組/頁面，例如 F0-2 角色管理頁面

    is_admin() 角色一律可見全部已啟用（enabled）的功能；一般角色需搭配 RolePermission.can_view。
    show_frontend / show_backend 控制這個功能出現在「前台」或「後台」導覽選單（可同時勾選兩者）。
    page_url 為 None 時代表這不是一個獨立頁面（例如 Dashboard 小工具），僅用於「啟用/停用」控制。
    """
    __tablename__ = "features"

    id = Column(String, primary_key=True, default=gen_id)
    code = Column(String, unique=True, nullable=False)   # e.g. F0-2
    module = Column(String, nullable=False)              # e.g. 目標零
    name = Column(String, nullable=False)                # e.g. 角色管理
    description = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    enabled = Column(Boolean, default=True, nullable=False)          # 總開關：停用後全站都看不到（含管理者）
    show_frontend = Column(Boolean, default=False, nullable=False)   # 顯示於前台導覽
    show_backend = Column(Boolean, default=True, nullable=False)     # 顯示於後台導覽
    nav_label = Column(String, nullable=True)             # 導覽選單顯示文字（空白時退回用 name）
    page_url = Column(String, nullable=True)              # 對應的獨立 HTML 頁面（None = 非頁面項目，如 Dashboard 小工具）
    sort_order = Column(Integer, default=0, nullable=False)

    permissions = relationship("RolePermission", back_populates="feature", cascade="all, delete-orphan")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "feature_id", name="uq_role_feature"),)

    id = Column(String, primary_key=True, default=gen_id)
    role_id = Column(String, ForeignKey("roles.id"), nullable=False)
    feature_id = Column(String, ForeignKey("features.id"), nullable=False)
    can_view = Column(Boolean, default=False)
    can_execute = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

    role = relationship("Role", back_populates="permissions")
    feature = relationship("Feature", back_populates="permissions")


class AccountApplication(Base):
    __tablename__ = "account_applications"

    id = Column(String, primary_key=True, default=gen_id)
    account = Column(String, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.pending)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_provider_account"),)

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(Enum(OAuthProvider), nullable=False)
    provider_user_id = Column(String, nullable=False)
    linked_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="oauth_accounts")


class AuditLog(Base):
    """稽核紀錄：僅新增與查詢，不提供刪除/修改，確保軌跡完整"""
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_id)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    actor_account = Column(String, nullable=True)
    action = Column(String, nullable=False)       # e.g. create_role / update_permission
    target_type = Column(String, nullable=True)   # e.g. role / user / permission
    target_id = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id = Column(String, primary_key=True, default=gen_id)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(Enum(BackupStatus), default=BackupStatus.running)
    file_path = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)


# ---------- 目標五：中藥行地理推薦 ----------

class PharmacyStatus(str, enum.Enum):
    active = "active"       # 上架顯示於前台
    inactive = "inactive"   # 下架（軟刪除）


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    business_hours = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    latitude = Column(String, nullable=False)   # 以字串儲存避免浮點精度問題，前端轉 float 使用
    longitude = Column(String, nullable=False)
    status = Column(Enum(PharmacyStatus), default=PharmacyStatus.active, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reviews = relationship("PharmacyReview", back_populates="pharmacy", cascade="all, delete-orphan")


class PharmacyReview(Base):
    __tablename__ = "pharmacy_reviews"
    __table_args__ = (UniqueConstraint("pharmacy_id", "user_id", name="uq_pharmacy_user_review"),)

    id = Column(String, primary_key=True, default=gen_id)
    pharmacy_id = Column(String, ForeignKey("pharmacies.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1~5
    comment = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)  # 管理者審核/管理備注
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    pharmacy = relationship("Pharmacy", back_populates="reviews")
    user = relationship("User")


# ---------- 目標一/二：TCMSP 藥材關聯資料庫（正式資料庫化，取代原本本機端 JSON 檔案） ----------

class TcmspHerb(Base):
    __tablename__ = "tcmsp_herbs"

    id = Column(Integer, primary_key=True)  # 沿用原始資料的 herb_id
    herb_cn_name = Column(String, nullable=True)
    herb_pinyin = Column(String, nullable=True)
    herb_en_name = Column(String, nullable=False, index=True)
    child_cn_name = Column(String, nullable=True)
    child_en_name = Column(String, nullable=True)
    status = Column(String, default="active", nullable=False)  # active / inactive（軟刪除）
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TcmspIngredient(Base):
    __tablename__ = "tcmsp_ingredients"

    mol_id = Column(String, primary_key=True)  # 例如 MOL000001
    molecule_name = Column(String, nullable=True)
    mw = Column(String, nullable=True)
    hdon = Column(String, nullable=True)
    hacc = Column(String, nullable=True)
    alogp = Column(String, nullable=True)
    halflife = Column(String, nullable=True)
    ob = Column(String, nullable=True)
    caco2 = Column(String, nullable=True)
    bbb = Column(String, nullable=True)
    dl = Column(String, nullable=True)
    fasa = Column(String, nullable=True)
    tpsa = Column(String, nullable=True)
    rbn = Column(String, nullable=True)
    source = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


class TcmspTarget(Base):
    __tablename__ = "tcmsp_targets"

    tar_id = Column(String, primary_key=True)  # 例如 TAR00002
    target_id = Column(Integer, nullable=True)
    drugbank_id = Column(String, nullable=True)
    target_name = Column(String, nullable=True)
    kegg = Column(String, nullable=True)
    source = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


class TcmspDisease(Base):
    __tablename__ = "tcmsp_diseases"

    dis_id = Column(String, primary_key=True)  # 例如 DIS00001
    disease_id = Column(Integer, nullable=True)
    disease_name = Column(String, nullable=True)
    disease_cn_name = Column(String, nullable=True)  # 中文名稱，可於後台補充/修正
    icd9 = Column(String, nullable=True)
    icd10 = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


class TcmspHerbIngredient(Base):
    __tablename__ = "tcmsp_herb_ingredient"
    __table_args__ = (UniqueConstraint("herb_id", "mol_id", name="uq_tcmsp_herb_mol"),)

    id = Column(String, primary_key=True, default=gen_id)
    herb_id = Column(Integer, ForeignKey("tcmsp_herbs.id"), nullable=False, index=True)
    mol_id = Column(String, ForeignKey("tcmsp_ingredients.mol_id"), nullable=False, index=True)


class TcmspIngredientTarget(Base):
    __tablename__ = "tcmsp_ingredient_target"
    __table_args__ = (UniqueConstraint("mol_id", "tar_id", name="uq_tcmsp_mol_tar"),)

    id = Column(String, primary_key=True, default=gen_id)
    mol_id = Column(String, ForeignKey("tcmsp_ingredients.mol_id"), nullable=False, index=True)
    tar_id = Column(String, ForeignKey("tcmsp_targets.tar_id"), nullable=False, index=True)
    validated = Column(String, nullable=True)
    svm_score = Column(String, nullable=True)
    rf_score = Column(String, nullable=True)


class TcmspTargetDisease(Base):
    __tablename__ = "tcmsp_target_disease"
    __table_args__ = (UniqueConstraint("tar_id", "dis_id", name="uq_tcmsp_tar_dis"),)

    id = Column(String, primary_key=True, default=gen_id)
    tar_id = Column(String, ForeignKey("tcmsp_targets.tar_id"), nullable=False, index=True)
    dis_id = Column(String, ForeignKey("tcmsp_diseases.dis_id"), nullable=False, index=True)


class UserPreference(Base):
    """使用者個人化設定（key-value，依 user_id 分開儲存），例如查詢站配色偏好"""
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_pref_key"),)

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    key = Column(String, nullable=False)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemSetting(Base):
    """通用系統設定（key-value），目前用於主題配色，未來其他全站設定也可共用這張表"""
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Announcement(Base):
    """公告：依 start_at/end_at 決定是否顯示於前台，時間到自動下架（不需要手動操作，查詢時即時判斷）"""
    __tablename__ = "announcements"

    id = Column(String, primary_key=True, default=gen_id)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    start_at = Column(DateTime, nullable=False)   # 開始顯示時間
    end_at = Column(DateTime, nullable=True)       # 結束顯示時間（None = 不自動下架，永久顯示直到手動下架）
    status = Column(String, default="active", nullable=False)  # active / inactive（管理者手動下架，軟刪除）
    notes = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    files = relationship("AnnouncementFile", back_populates="announcement", cascade="all, delete-orphan")


class AnnouncementFile(Base):
    """公告附件：內容直接以 base64 存資料庫（避免 Render 免費方案檔案系統不持久的問題，Neon 才是唯一可靠儲存）"""
    __tablename__ = "announcement_files"

    id = Column(String, primary_key=True, default=gen_id)
    announcement_id = Column(String, ForeignKey("announcements.id"), nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_data_base64 = Column(Text, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    announcement = relationship("Announcement", back_populates="files")


class Patient(Base):
    """病患基本資料。欄位參照中國國家衛健委《電子病歷基本數據集》標準命名，
    屬於敏感個資（PII），id_number 這類欄位在 API 回傳時一律遮罩，
    需要透過專門的「顯示完整證件號碼」端點才能看到明碼，且會記錄稽核紀錄。
    這是目標三（DNA檢測/精準醫療）與目標四（中藥複方建議）的基礎資料層，
    正式提供醫療建議前仍需要醫師/專業人員審核機制（詳見 rules.md／docs/2026_goals.md）。
    """
    __tablename__ = "patients"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, unique=True, nullable=False)   # 病患院內唯一識別碼
    id_type = Column(String, nullable=True)                    # 證件類型（身分證/護照/居留證...）
    id_number = Column(String, nullable=True)                  # 證件號碼（明碼儲存，API 回傳一律遮罩）
    name = Column(String, nullable=False)
    sex_code = Column(String, nullable=True)                   # 性別代碼
    birth_date = Column(String, nullable=True)                 # 出生日期（YYYY-MM-DD）
    nationality_code = Column(String, nullable=True)
    ethnicity_code = Column(String, nullable=True)              # 民族
    address = Column(String, nullable=True)
    telephone = Column(String, nullable=True)
    medical_record_no = Column(String, nullable=True)           # 病歷號
    status = Column(String, default="active", nullable=False)   # active / inactive（軟刪除）
    notes = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    encounters = relationship("Encounter", back_populates="patient", cascade="all, delete-orphan")


class Encounter(Base):
    """就診紀錄（對應病患-就診-檢體-定序-分析-變異-解讀-品質八層資料模型中的「就診」層）。
    其餘六層（檢體/定序/分析/變異/解讀/品質）屬於目標三 DNA 檢測範疇，規劃於後續版本擴充。
    """
    __tablename__ = "encounters"

    id = Column(String, primary_key=True, default=gen_id)
    encounter_id = Column(String, unique=True, nullable=False)  # 就診識別碼
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    medical_institution = Column(String, nullable=True)          # 醫療機構
    department = Column(String, nullable=True)                   # 科別
    diagnosis_code = Column(String, nullable=True)                # 診斷代碼
    diagnosis_name = Column(String, nullable=True)
    encounter_date = Column(String, nullable=True)                # 就診日期（YYYY-MM-DD）
    status = Column(String, default="active", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="encounters")


class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    account = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    device_id = Column(String, nullable=True)     # 網卡編號／裝置識別碼（前端可傳送，瀏覽器環境僅能取得有限資訊）
    user_agent = Column(String, nullable=True)
    login_at = Column(DateTime, default=datetime.utcnow)
    logout_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
