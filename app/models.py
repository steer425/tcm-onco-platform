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
    opens_at = Column(String, nullable=True)     # 結構化營業時間（HH:MM），供「營業狀態」判斷用
    closes_at = Column(String, nullable=True)    # 結構化營業時間（HH:MM）
    description = Column(Text, nullable=True)
    latitude = Column(String, nullable=False)   # 以字串儲存避免浮點精度問題，前端轉 float 使用
    longitude = Column(String, nullable=False)
    status = Column(Enum(PharmacyStatus), default=PharmacyStatus.active, nullable=False)
    notes = Column(Text, nullable=True)

    # 熱門程度／統計欄位
    view_count = Column(Integer, default=0, nullable=False)
    favorite_count = Column(Integer, default=0, nullable=False)
    share_count = Column(Integer, default=0, nullable=False)
    nav_click_count = Column(Integer, default=0, nullable=False)  # 使用者按「路線規劃/導航」的次數

    # 店家功能（後台，店家自行維護）
    opening_date = Column(String, nullable=True)          # 開幕日期（YYYY-MM-DD），沒填就用 created_at 當「上架日期」排序
    discount_percent = Column(Integer, nullable=True)      # 折扣幅度（例如輸入 20 代表 8 折 / 20% off）
    discount_description = Column(String, nullable=True)   # 優惠說明文字
    discount_valid_until = Column(String, nullable=True)   # 優惠期限（YYYY-MM-DD），為空代表長期有效

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reviews = relationship("PharmacyReview", back_populates="pharmacy", cascade="all, delete-orphan")
    checkins = relationship("PharmacyCheckin", back_populates="pharmacy", cascade="all, delete-orphan")


class PharmacyCheckin(Base):
    """中藥行打卡紀錄，附帶本次消費金額（供「價格水準」統計使用）"""
    __tablename__ = "pharmacy_checkins"

    id = Column(String, primary_key=True, default=gen_id)
    pharmacy_id = Column(String, ForeignKey("pharmacies.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    spending_amount = Column(Integer, nullable=True)  # 本次消費金額（新台幣），選填
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pharmacy = relationship("Pharmacy", back_populates="checkins")


class PharmacyFavorite(Base):
    """使用者收藏的中藥行"""
    __tablename__ = "pharmacy_favorites"
    __table_args__ = (UniqueConstraint("pharmacy_id", "user_id", name="uq_pharmacy_favorite"),)

    id = Column(String, primary_key=True, default=gen_id)
    pharmacy_id = Column(String, ForeignKey("pharmacies.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


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
    # 以下兩個欄位是預先計算好存起來的統計數字，不是每次查詢站列表載入時即時運算：
    # target_count：這個藥材（透過成分）連結到幾個不重複的 TCMSP 靶點
    # dark_gene_count：這個藥材（透過成分-靶點）連結到幾個不重複的暗黑基因
    # 由 app/recompute_stats.py 統一重算，資料匯入後跑一次即可，查詢時直接讀欄位、不用現場算
    target_count = Column(Integer, default=0, nullable=False)
    dark_gene_count = Column(Integer, default=0, nullable=False)
    # 這個藥材（透過成分-靶點）連結到幾個不重複的 GenCC 可編碼蛋白區疾病（見 GenccDisease）
    gencc_disease_count = Column(Integer, default=0, nullable=False)
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
    # 預先計算好的統計數字：這個疾病連結到幾個不重複的 TCMSP 靶點，
    # 由 app/recompute_stats.py 統一重算，查詢站列表不用現場運算
    target_count = Column(Integer, default=0, nullable=False)


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


class DarkGene(Base):
    """暗黑基因（癌症相關基因參考資料）。資料來源：OncoKB 癌症基因列表（公開參考資料集）。
    對應目標三（NVIDIA BioNeMo + Google AlphaGenome 暗黑基因組分析）的基礎參考資料層。
    正式串接 AlphaGenome 進行基因預測前，仍需要專業人員/醫師審核機制，
    詳見 rules.md／docs/2026_goals.md 已記錄的規劃與法規限制。
    """
    __tablename__ = "dark_genes"

    id = Column(String, primary_key=True, default=gen_id)
    hugo_symbol = Column(String, unique=True, nullable=False, index=True)  # 基因符號，例如 ABL1
    entrez_gene_id = Column(String, nullable=True)
    grch37_isoform = Column(String, nullable=True)
    grch37_refseq = Column(String, nullable=True)
    grch38_isoform = Column(String, nullable=True)
    grch38_refseq = Column(String, nullable=True)
    gene_type = Column(String, nullable=True)  # ONCOGENE / TSG / ONCOGENE_AND_TSG / NEITHER / INSUFFICIENT_EVIDENCE
    occurrence_count = Column(Integer, nullable=True)  # 在幾個資源清單中出現（Column K-P 統計）
    oncokb_annotated = Column(Boolean, default=False, nullable=False)
    msk_impact = Column(Boolean, default=False, nullable=False)
    msk_heme = Column(Boolean, default=False, nullable=False)
    foundation_one = Column(Boolean, default=False, nullable=False)
    foundation_one_heme = Column(Boolean, default=False, nullable=False)
    vogelstein = Column(Boolean, default=False, nullable=False)
    cosmic_cgc = Column(Boolean, default=False, nullable=False)
    gene_aliases = Column(Text, nullable=True)
    # 預先計算好的比對結果：這個基因是否比對到 TCMSP 靶點資料，
    # 由 app/recompute_stats.py 統一重算（用基因符號/別名比對靶點名稱），
    # 查詢站列表直接讀這個欄位，不用每次請求都重新掃一次全部靶點
    has_tcmsp_target = Column(Boolean, default=False, nullable=False)
    status = Column(String, default="active", nullable=False)  # active / inactive（軟刪除）
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GenccDisease(Base):
    """可編碼蛋白區中藥與疾病關聯：資料來源 GenCC（Gene Curation Coalition，https://thegencc.org/download）。
    GenCC 彙整多個專家審查小組（ClinGen、PanelApp 等）對「基因-疾病因果關係」的評估結果，
    每筆是一個「基因 → 疾病」的斷言（assertion），附帶信心等級（classification）與遺傳模式（mode of inheritance）。

    跟暗黑基因（DarkGene / OncoKB）不同的地方：暗黑基因是「癌症相關基因清單」（沒有對應到特定疾病），
    這裡的每一筆資料本身就同時包含基因跟疾病兩個維度，比對邏輯是拿 gene_symbol 去比對 TCMSP 靶點名稱
    （跟暗黑基因用同一套字詞比對演算法），藉此建立「基因 → 靶點 → 成分 → 藥材」的機制層級關聯鏈，
    畫面設計比照暗黑基因查詢站。

    資料量遠大於暗黑基因（GenCC 完整資料集通常有 1.5~2 萬筆斷言，暗黑基因只有 1245 筆），
    所以 has_tcmsp_target 統計一律走 app/recompute_stats.py 預先計算好存欄位的模式，
    不能像早期查詢端點那樣即時運算（會直接拖垮回應速度，這是這個系統踩過好幾次的教訓，見 rules.md）。

    這是研究層級的基因-疾病關聯參考資料，不是臨床診斷依據；跟暗黑基因一樣，正式提供醫療建議前
    仍需要專業人員/醫師審核機制。
    """
    __tablename__ = "gencc_diseases"

    id = Column(String, primary_key=True, default=gen_id)
    sgc_id = Column(String, unique=True, nullable=False, index=True)  # GenCC 新格式的唯一識別碼，例如 SGC-100001
    version_number = Column(String, nullable=True)
    gene_curie = Column(String, nullable=True, index=True)  # HGNC:XXXXX
    gene_symbol = Column(String, nullable=False, index=True)  # 基因符號，例如 SKI（用這個欄位比對 TCMSP 靶點）
    disease_curie = Column(String, nullable=True)  # MONDO:XXXXXXX
    disease_title = Column(String, nullable=True)  # 疾病名稱（小寫可讀格式）
    disease_original_curie = Column(String, nullable=True)  # OMIM:XXXXXX（原始提交來源編號）
    disease_original_title = Column(String, nullable=True)  # 原始提交的疾病名稱（通常是 OMIM 大寫格式）
    disease_cn_name = Column(String, nullable=True)  # 中文名稱（繁體），可於後台補充/修正（比照 TcmspDisease 的做法）
    # 以下兩個欄位是額外新增的：疾病名稱不像藥材/成分名稱那樣可以單純用 OpenCC 字形轉換就好
    # （醫學疾病名稱的繁簡用詞習慣常常不只是字形不同，簡體中文醫學文獻慣用語有時跟繁體字形轉換結果不一致），
    # 也沒有現成的韓文機器翻譯資源可用，所以這三種語言的疾病名稱各自獨立儲存、後台個別編輯，
    # 不是像藥材/疾病（TCMSP）那樣繁體存一份、簡體用 OpenCC 即時轉換、韓文乾脆不翻。
    disease_name_cn = Column(String, nullable=True)  # 中文名稱（簡體），獨立儲存，不是自動轉換
    disease_name_ko = Column(String, nullable=True)  # 疾病名稱（韓文），獨立儲存
    classification_curie = Column(String, nullable=True)  # GENCC:XXXXXX
    classification_title = Column(String, nullable=True, index=True)  # Definitive / Strong / Moderate / Limited / Disputed Evidence / Refuted Evidence / No Known Disease Relationship / Supportive
    moi_curie = Column(String, nullable=True)  # HP:XXXXXXX
    moi_title = Column(String, nullable=True)  # 遺傳模式，例如 Autosomal dominant
    submitter_title = Column(String, nullable=True)  # 提交的專家審查小組名稱，例如 ClinGen
    submitted_as_pmids = Column(Text, nullable=True)  # 文獻佐證（PMID 或連結）
    # 預先計算好的比對結果：這個基因是否比對到 TCMSP 靶點資料，
    # 由 app/recompute_stats.py 統一重算，查詢站列表直接讀這個欄位，不用每次請求都即時運算
    has_tcmsp_target = Column(Boolean, default=False, nullable=False)
    status = Column(String, default="active", nullable=False)  # active / inactive（軟刪除）
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Specimen(Base):
    """檢體。對應病患-就診-檢體-定序-分析-變異-解讀-品質八層資料模型的「檢體」層。"""
    __tablename__ = "specimens"

    id = Column(String, primary_key=True, default=gen_id)
    specimen_no = Column(String, unique=True, nullable=False)  # 檢體編號
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    encounter_id = Column(String, ForeignKey("encounters.id"), nullable=True)
    specimen_type = Column(String, nullable=True)   # 檢體種類（血液/組織/唾液...）
    tissue_site = Column(String, nullable=True)      # 組織部位
    tumor_normal = Column(String, nullable=True)      # tumor / normal
    collection_date = Column(String, nullable=True)
    status = Column(String, default="active", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    batches = relationship("DnaImportBatch", back_populates="specimen", cascade="all, delete-orphan")


class DnaImportBatch(Base):
    """DNA 資料匯入批次。同一位病患可以有多筆匯入紀錄（例如不同時間點送驗），
    每筆匯入都會保留成獨立批次，方便「多次匯入比較」。"""
    __tablename__ = "dna_import_batches"

    id = Column(String, primary_key=True, default=gen_id)
    batch_no = Column(String, unique=True, nullable=False)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    specimen_id = Column(String, ForeignKey("specimens.id"), nullable=True)
    source_type = Column(String, default="import", nullable=False)  # import（真實匯入）/ synthetic（測試資料產生）
    source_filename = Column(String, nullable=True)
    platform = Column(String, nullable=True)          # 定序平台
    panel = Column(String, nullable=True)              # 檢測 panel
    reference_genome = Column(String, nullable=True)   # 參考基因組版本（GRCh37/38）
    pipeline_info = Column(String, nullable=True)       # pipeline 名稱與版本
    variant_count = Column(Integer, default=0, nullable=False)
    status = Column(String, default="active", nullable=False)
    notes = Column(Text, nullable=True)
    imported_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    specimen = relationship("Specimen", back_populates="batches")
    variants = relationship("Variant", back_populates="batch", cascade="all, delete-orphan")


class Variant(Base):
    """基因變異紀錄（對應「變異」＋簡化整合「品質」「解讀」欄位，避免拆太多張表）。
    gene_symbol 對應 dark_genes.hugo_symbol，用來判斷是否命中暗黑基因清單。"""
    __tablename__ = "variants"

    id = Column(String, primary_key=True, default=gen_id)
    batch_id = Column(String, ForeignKey("dna_import_batches.id"), nullable=False)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)  # 為了查詢方便而冗余存一份
    chromosome = Column(String, nullable=True)
    position = Column(String, nullable=True)
    ref_allele = Column(String, nullable=True)
    alt_allele = Column(String, nullable=True)
    gene_symbol = Column(String, nullable=True, index=True)  # 對應 dark_genes.hugo_symbol
    hgvs = Column(String, nullable=True)
    vcf_version = Column(String, nullable=True)
    depth = Column(Integer, nullable=True)               # 品質欄位：定序深度
    allele_fraction = Column(String, nullable=True)        # 品質欄位：變異等位基因比例
    qc_status = Column(String, nullable=True)              # 品質欄位：pass / fail / warn
    clinical_significance = Column(String, nullable=True)  # 解讀欄位（僅供研究參考，非臨床判讀）
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    batch = relationship("DnaImportBatch", back_populates="variants")


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


# ===========================================================================
# 每日重點新聞模組（中藥與腫瘤｜10 個權威官方追蹤網站）
# ---------------------------------------------------------------------------
# 定位：科研輔助情報，服務於證據查證、安全監測與研究追蹤，
#       不作為醫療診斷或治療建議。
#
# 設計說明：
#   * 沿用全站慣例：String(uuid) 主鍵、可攜型別（不用 PostgreSQL 專屬的
#     ENUM/ARRAY/JSONB/INET），確保本機 SQLite 退回模式仍可運作。
#   * 管理者操作紀錄不另建表，一律寫進現成的 AuditLog（write_audit_log）。
#   * 陣列型資料（癌別、標籤等）以 JSON 字串存在 Text 欄位，
#     由 schemas 層負責序列化/反序列化。
# ===========================================================================


class NewsCollectorKind(str, enum.Enum):
    api = "api"          # 官方 API（PubMed E-utilities、ClinicalTrials.gov v2）
    rss = "rss"          # RSS/Atom（WHO、NCI）
    scrape = "scrape"    # HTML 爬蟲（NCCIH、OCCAM、MSK、NHC、SATCM）


class NewsEvidenceLevel(str, enum.Enum):
    """對應追蹤指南的證據層級分類，決定前台標籤與排序權重。"""
    policy_global = "policy_global"          # 政策與全球標準（WHO）
    clinical_evidence = "clinical_evidence"  # 癌症臨床與實證（NCI）
    research_policy = "research_policy"      # 研究政策與資助（OCCAM）
    natural_product = "natural_product"      # 天然物研究與安全（NCCIH）
    literature_index = "literature_index"    # 學術文獻索引（PubMed）
    trial_registry = "trial_registry"        # 臨床試驗登錄（ClinicalTrials.gov）
    cancer_center = "cancer_center"          # 癌症中心臨床實務（MSK）
    herb_safety = "herb_safety"              # 草藥安全與交互作用（About Herbs）
    national_policy = "national_policy"      # 國家衛生政策（中國衛健委）
    tcm_policy = "tcm_policy"                # 中醫藥國家政策（中醫藥管理局）
    # 管理者自行新增的一般新聞來源。刻意獨立一個層級而不是硬塞進上面任何一個：
    # 卡片上會顯示層級標籤，把商業新聞標成「癌症臨床與實證」會直接誤導讀者。
    general_news = "general_news"            # 一般新聞（後台自行新增）


class NewsEvidenceMaturity(str, enum.Enum):
    """證據成熟度。preclinical 會被降權，且前台強制顯示「不可推論至病患層級」。"""
    human = "human"
    mixed = "mixed"
    preclinical = "preclinical"
    unknown = "unknown"


class NewsArticleStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    deleted = "deleted"


class NewsRunStatus(str, enum.Enum):
    running = "running"
    success = "success"
    partial = "partial"
    failed = "failed"


class NewsEntityType(str, enum.Enum):
    """新聞內文比對到的平台實體種類，供前台產生可點連結。"""
    herb = "herb"
    ingredient = "ingredient"
    target = "target"
    disease = "disease"


class NewsSource(Base):
    """10 個權威官方追蹤來源。爬蟲選擇器等設定放在 config（JSON 字串），
    來源改版時於後台修改即可，不需改程式重新部署。"""
    __tablename__ = "news_sources"

    id = Column(String, primary_key=True, default=gen_id)
    slug = Column(String, unique=True, nullable=False, index=True)
    name_zh = Column(String, nullable=False)
    name_en = Column(String, nullable=False)
    homepage = Column(String, nullable=False)
    kind = Column(Enum(NewsCollectorKind), nullable=False)
    evidence_level = Column(Enum(NewsEvidenceLevel), nullable=False)
    # 來源權威度（0~1），參與排序加權
    weight = Column(String, nullable=False, default="0.50")
    lang = Column(String, nullable=False, default="en")
    # True 表示來源查詢式本身已鎖定主題，可略過關鍵字硬過濾
    prefiltered = Column(Boolean, nullable=False, default=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    # True = 管理者在後台自行新增的來源（不在 sources.py 的註冊表裡）。
    # sync_sources() 只同步程式碼定義的來源，看到 is_custom 一律不碰；
    # 刪除也只允許刪 is_custom 的，避免有人在後台把官方來源刪掉之後
    # 下次部署又被 sync 回來，造成「刪了又出現」的鬼打牆。
    is_custom = Column(Boolean, nullable=False, default=False, index=True)
    config = Column(Text, nullable=True)          # JSON 字串
    notes = Column(Text, nullable=True)
    # 健康度追蹤：連續失敗次數超過門檻時後台亮警示
    last_success_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(String, primary_key=True, default=gen_id)
    source_id = Column(String, ForeignKey("news_sources.id"), nullable=False, index=True)

    # ---- 識別與去重 ----
    url = Column(Text, nullable=False)
    url_hash = Column(String, nullable=False, unique=True, index=True)   # sha256(正規化 URL)
    content_hash = Column(String, nullable=True, index=True)             # sha256(標題+摘要)
    title_simhash = Column(String, nullable=True)                        # 64-bit 以 16 進位字串存
    external_id = Column(String, nullable=True, index=True)              # PMID / NCT
    doi = Column(String, nullable=True)

    # ---- 內容 ----
    title = Column(Text, nullable=False)
    title_zh = Column(Text, nullable=True)
    abstract = Column(Text, nullable=True)
    summary_zh = Column(Text, nullable=True)
    key_points = Column(Text, nullable=True)      # JSON 陣列字串
    caveat_zh = Column(Text, nullable=True)       # 解讀注意事項（必附）
    authors = Column(Text, nullable=True)
    journal = Column(String, nullable=True)
    lang = Column(String, nullable=True)

    # ---- 分類 ----
    evidence_level = Column(Enum(NewsEvidenceLevel), nullable=False)
    evidence_maturity = Column(Enum(NewsEvidenceMaturity), nullable=False,
                               default=NewsEvidenceMaturity.unknown)
    study_design = Column(String, nullable=True)
    cancer_types = Column(Text, nullable=True)        # JSON 陣列字串
    intervention_types = Column(Text, nullable=True)  # JSON 陣列字串
    tags = Column(Text, nullable=True)                # JSON 陣列字串
    is_safety_signal = Column(Boolean, nullable=False, default=False, index=True)

    # ---- 未解禁（embargo）----
    # 部分臨床研究來源在正式公開前會有禁運期限制；未解禁內容一般使用者查不到，
    # 只有管理者或擁有 F0-20 can_view 權限的角色可提早查閱（見 app/deps.py 的 has_permission()）。
    is_embargoed = Column(Boolean, nullable=False, default=False, index=True)
    embargo_until = Column(DateTime, nullable=True)

    # ---- 排序 ----
    relevance_score = Column(String, nullable=False, default="0")
    rank_score = Column(String, nullable=False, default="0")

    # ---- 時間 ----
    published_at = Column(DateTime, nullable=True, index=True)
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)
    source_updated_at = Column(DateTime, nullable=True)

    # ---- 狀態與軟刪除（管理者刪除舊新聞時強制填註記）----
    status = Column(Enum(NewsArticleStatus), nullable=False,
                    default=NewsArticleStatus.active, index=True)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(String, ForeignKey("users.id"), nullable=True)
    delete_note = Column(Text, nullable=True)

    raw_payload = Column(Text, nullable=True)   # 原始回傳 JSON，供追溯
    # 後台查詢用：title + title_zh + summary_zh + abstract + 識別碼，全轉小寫。
    # 不用全文索引是因為中文斷詞在 SQLite/PostgreSQL 兩邊行為不一致，
    # 本模組一年約 3,650 筆，單欄 LIKE 掃描成本可忽略。
    search_blob = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NewsArticleEntity(Base):
    """新聞內文比對到的平台實體，讓讀者可以從新聞點進查詢站。

    四種 id 欄位只會有一個有值（依 entity_type 決定），保留真實外鍵，
    因此可以直接 join 回主檔做統計，也能安全地產生連結。
    """
    __tablename__ = "news_article_entities"
    __table_args__ = (
        UniqueConstraint("article_id", "entity_type", "entity_key",
                         name="uq_news_article_entity"),
    )

    id = Column(String, primary_key=True, default=gen_id)
    article_id = Column(String, ForeignKey("news_articles.id"), nullable=False, index=True)
    entity_type = Column(Enum(NewsEntityType), nullable=False, index=True)
    # entity_key 是該實體主鍵的字串形式，用於唯一約束（herb 是 Integer，其餘是 String）
    entity_key = Column(String, nullable=False)

    herb_id = Column(Integer, ForeignKey("tcmsp_herbs.id"), nullable=True, index=True)
    mol_id = Column(String, ForeignKey("tcmsp_ingredients.mol_id"), nullable=True, index=True)
    tar_id = Column(String, ForeignKey("tcmsp_targets.tar_id"), nullable=True, index=True)
    dis_id = Column(String, ForeignKey("tcmsp_diseases.dis_id"), nullable=True, index=True)

    display_name = Column(String, nullable=True)   # 顯示用名稱（中文優先）
    matched_text = Column(String, nullable=True)   # 原文實際命中的字串
    match_type = Column(String, nullable=True)     # exact_en / exact_cn / pinyin / alias
    created_at = Column(DateTime, default=datetime.utcnow)


class NewsDailyDigest(Base):
    """每日重點新聞（預設每天 10 篇，篇數可由 news_settings 調整）。"""
    __tablename__ = "news_daily_digests"
    __table_args__ = (
        UniqueConstraint("digest_date", "article_id", name="uq_news_digest_date_article"),
    )

    id = Column(String, primary_key=True, default=gen_id)
    digest_date = Column(String, nullable=False, index=True)   # 'YYYY-MM-DD'（Asia/Taipei）
    article_id = Column(String, ForeignKey("news_articles.id"), nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    rank_score = Column(String, nullable=False, default="0")
    pick_reason = Column(Text, nullable=True)     # AI/系統說明為何入選
    is_pinned = Column(Boolean, nullable=False, default=False)  # 置頂項目不會被隔日重跑覆蓋
    created_at = Column(DateTime, default=datetime.utcnow)


class UserNewsBookmark(Base):
    """使用者勾選保留的新聞。被保留的文章不會被管理者的批次刪除影響。"""
    __tablename__ = "user_news_bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_user_news_bookmark"),
    )

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    article_id = Column(String, ForeignKey("news_articles.id"), nullable=False, index=True)
    folder = Column(String, nullable=False, default="default")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class NewsCollectionRun(Base):
    """每日收集執行紀錄，供後台查詢與排查來源異常。"""
    __tablename__ = "news_collection_runs"

    id = Column(String, primary_key=True, default=gen_id)
    run_date = Column(String, nullable=False, index=True)     # 'YYYY-MM-DD'
    trigger_type = Column(String, nullable=False, default="scheduled")  # scheduled/manual/backfill
    triggered_by = Column(String, ForeignKey("users.id"), nullable=True)
    status = Column(Enum(NewsRunStatus), nullable=False, default=NewsRunStatus.running)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    fetched_count = Column(Integer, nullable=False, default=0)
    new_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    filtered_count = Column(Integer, nullable=False, default=0)
    digest_count = Column(Integer, nullable=False, default=0)
    linked_entity_count = Column(Integer, nullable=False, default=0)
    per_source = Column(Text, nullable=True)      # JSON：{slug: {fetched, error}}
    error_message = Column(Text, nullable=True)


class NewsSetting(Base):
    """新聞模組設定（每日篇數、相關度門檻、免責聲明等）。"""
    __tablename__ = "news_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)          # JSON 字串
    description = Column(String, nullable=True)
    updated_by = Column(String, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NewsArticleSummary(Base):
    """每篇新聞的多語系「簡短摘要」（預設 200 字，長度可由 news_settings 調整）。

    刻意獨立成一張表，而不是在 news_articles 直接加 summary_en／summary_ko 欄位：

    1. 語系是會長大的。之後要加日文只是多寫入一列，不用 ALTER TABLE，
       也不會讓 news_articles 每加一個語系就寬一截。
    2. 多數文章只會被少數語系讀到。獨立成表才有辦法「有人真的用那個語系看，
       才產生那個語系的摘要」，不必每篇都先付 N 個語系的 API 費用。
    3. 摘要有自己的生命週期（字數上限改了要重產、模型換了要重產），
       把 char_limit／model 記在同一列，之後才判斷得出哪些需要重新產生。

    `lang` 只存「真的需要各自生成」的語系：'zh-TW'／'en'／'ko'。
    簡體中文刻意不存——前端全站語系機制已經用 OpenCC 做繁→簡字形轉換
    （見 frontend/js/site-lang.js），簡中直接沿用繁中這一列即可，
    再花一次 API 費用產簡體是重複投資。
    """
    __tablename__ = "news_article_summaries"
    __table_args__ = (
        UniqueConstraint("article_id", "lang", name="uq_news_summary_article_lang"),
    )

    id = Column(String, primary_key=True, default=gen_id)
    article_id = Column(String, ForeignKey("news_articles.id"), nullable=False, index=True)
    lang = Column(String, nullable=False, index=True)     # 'zh-TW' / 'en' / 'ko'
    summary = Column(Text, nullable=False)
    char_limit = Column(Integer, nullable=False)          # 產生當下的字數上限，供日後判斷要不要重產
    is_ai = Column(Boolean, nullable=False, default=False)  # False = 降級的規則式截斷
    model = Column(String, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)


class NewsKeyword(Base):
    """主題過濾關鍵字（中藥詞 × 腫瘤詞），管理者可於後台維護。

    為什麼要進資料庫：新增一個新聞來源之後，最常需要調整的就是這兩組詞——
    來源換了，用語就換了（例如中文站講「中成藥」「驗方」，英文站講 botanical、
    phytotherapy）。這件事不該每次都要改程式重新部署。

    只收「主題過濾」這兩組。癌別對照、介入方式、臨床前判定詞刻意留在程式裡：
    那幾組直接影響證據層級判斷與排序哲學，改壞了會讓臨床前研究排到人體試驗前面，
    不是日常維護該碰的東西。

    `group` 只有 'tcm' 與 'cancer' 兩種。一篇文章要同時命中兩組才算相關
    （見 scoring.relevance()），所以兩組都不能是空的——刪到最後一筆會被擋下來。
    """
    __tablename__ = "news_keywords"
    __table_args__ = (
        UniqueConstraint("group", "term", name="uq_news_keyword_group_term"),
    )

    id = Column(String, primary_key=True, default=gen_id)
    group = Column(String, nullable=False, index=True)   # 'tcm' / 'cancer'
    term = Column(String, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    # True = 隨程式碼一起帶進來的預設詞。允許停用或刪除，但介面上會標示出來，
    # 讓管理者知道這是原廠設定而不是自己加的。
    is_default = Column(Boolean, nullable=False, default=False)
    note = Column(String, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TcmspTargetUniprot(Base):
    """TCMSP 靶點 → UniProt 標準化映射（目標一 Step 3）。

    為什麼需要這張表：TCMSP 的 1751 個靶點裡有 1573 個是**蛋白全名**
    （「Androgen receptor」「RAC-alpha serine/threonine-protein kinase」），
    只有 4 個長得像基因符號。而暗黑基因、GenCC 疾病關聯、新聞實體連結
    全都是拿「基因符號」去比對靶點名稱字串——「Androgen receptor」這串字裡
    永遠不會出現 AR，所以那三個功能看到的都是嚴重失真的結果。

    實測（標準化前）：1245 個癌症基因只比對到 32 個（2.6%），而 AR／AKT1／TP53／APC／
    EGFR／ESR1／PTGS2 全都在 TCMSP 裡、全都比對不到。而且失真是靜默的——
    畫面不會顯示「比對失敗」，只會顯示「沒有關聯」。

    v1.38.0 上線後實測（2026-08-27）：1265／1751 標準化（72.2%），
    比對率 2.6% → **18.0%（224/1245）**。18% 已接近真實上限——TCMSP 的靶點
    偏向可成藥蛋白，OncoKB 癌症基因裡有大量 undruggable 的轉錄因子與染色質因子，
    兩個集合重疊 18% 是合理的，不要當成還沒做完而硬追。

    刻意獨立成表，不在 tcmsp_targets 加欄位：

    1. **不動原始 TCMSP 資料**，跟 recompute_stats.py 同一個原則。
       重新匯入 TCMSP 時映射不會被洗掉，也隨時可以整張丟掉重來。
    2. 映射有**來源與可信度**（哪一級策略解出來的、有沒有人確認過），
       這些是映射自己的屬性，不是靶點的屬性。
    3. 一個靶點可能合法對到多筆（「Estrogen receptor」→ ESR1／ESR2），
       塞進單一欄位就得做取捨，而那個取捨應該由人來做。

    TCMSP 原本的 `drugbank_id` 其實是流水號（3、7、16…）不是 DrugBank ID，
    `kegg` 欄位只有 11 筆有值——兩者都不能當外部識別碼，所以只能走名稱解析。
    """
    __tablename__ = "tcmsp_target_uniprot"
    __table_args__ = (
        UniqueConstraint("tar_id", "accession", name="uq_tcmsp_target_uniprot"),
    )

    id = Column(String, primary_key=True, default=gen_id)
    tar_id = Column(String, ForeignKey("tcmsp_targets.tar_id"), nullable=False, index=True)

    accession = Column(String, nullable=True, index=True)     # P10275
    gene_symbol = Column(String, nullable=True, index=True)   # AR
    gene_synonyms = Column(Text, nullable=True)               # JSON 陣列字串
    protein_name = Column(Text, nullable=True)                # UniProt 的正式名稱
    organism_id = Column(Integer, nullable=True)              # 9606 = 人類

    # UniProt 回應裡本來就帶的交叉引用。順手存下來，
    # 通路富集分析（A 組下一項）就不必再跑一次解析。
    kegg_id = Column(String, nullable=True)                   # hsa:367
    reactome_ids = Column(Text, nullable=True)                # JSON 陣列字串

    # exact（精確名稱）/ stripped（去修飾語）/ fulltext（全文查詢）/ manual（人工指定）
    method = Column(String, nullable=False, default="exact")
    confidence = Column(String, nullable=False, default="0")  # 0..1，字串存以維持可攜
    # auto（自動採用）/ pending（待人工確認）/ confirmed / rejected / unresolved（查無）
    status = Column(String, nullable=False, default="auto", index=True)
    candidates = Column(Text, nullable=True)                  # 待確認時的候選清單（JSON）
    note = Column(Text, nullable=True)

    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Pathway(Base):
    """訊號通路／代謝通路主檔（KEGG 與 Reactome，目標一 Step 4）。

    資料從哪來：v1.38.0 解析 UniProt 時，順手把每個靶點的 `kegg_id`（`hsa:367`）
    與 `reactome_ids`（`R-HSA-383280`）一起存進 `tcmsp_target_uniprot` 了。
    1751 個靶點裡有 1258 個帶 KEGG 交叉引用——通路分析最貴的那一步
    （把蛋白對應到通路識別碼）等於已經完成，這張表只是把通路本身的
    名稱、分類與背景基因數補上。

    **注意 KEGG 的兩種識別碼不要搞混**：
      - `hsa:367` 是 KEGG **基因** ID（就是 UniProt 交叉引用給的那個）
      - `hsa04915` 才是 KEGG **通路** ID（這張表存的）
    兩者之間的對應要另外向 KEGG 要（`rest.kegg.jp/link/pathway/hsa`，一次整包）。
    Reactome 則不必：UniProt 的 Reactome 交叉引用給的本來就是通路 ID。

    `background_gene_count` 是富集檢定的分母之一（該通路在**全人類基因**裡有幾個成員），
    必須來自資料庫本身而不是我們手上的靶點——拿我們自己的資料當母體會讓
    每個通路看起來都「富集」，那是統計上的循環論證。
    """
    __tablename__ = "pathways"
    __table_args__ = (
        UniqueConstraint("source", "pathway_id", name="uq_pathway_source_id"),
    )

    id = Column(String, primary_key=True, default=gen_id)
    source = Column(String, nullable=False, index=True)      # kegg / reactome
    pathway_id = Column(String, nullable=False, index=True)  # hsa04915 / R-HSA-383280
    name = Column(Text, nullable=False)

    # 三語系獨立儲存，不用 OpenCC／字典轉換——通路名稱是專有名詞，
    # 字形轉換會產出「訊號傳導」這種看似正確但不是慣用譯名的結果（GenCC 那邊踩過）
    name_cn = Column(Text, nullable=True)
    name_tw = Column(Text, nullable=True)
    name_ko = Column(Text, nullable=True)

    category = Column(Text, nullable=True)   # KEGG class／Reactome 上層事件
    is_cancer_related = Column(Boolean, default=False, index=True)
    background_gene_count = Column(Integer, nullable=True)   # 全人類基因中的成員數
    synced_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TargetPathway(Base):
    """TCMSP 靶點 ↔ 通路關聯（由 tcmsp_target_uniprot 的交叉引用推導而來）。

    跟 `tcmsp_target_uniprot` 一樣是**推導出來的資料**，不是原始資料：
    整張表隨時可以清掉重建，重建來源是映射表 + 通路主檔，不需要重新解析 UniProt。

    `via_symbol` 記錄「是靠哪個基因符號連上的」。看起來多餘，
    但沒有它就無法回答「這條連結是怎麼來的」——而通路富集的結果是要寫進
    研究報告的，每一條連結都必須追得回源頭。
    """
    __tablename__ = "target_pathways"
    __table_args__ = (
        UniqueConstraint("tar_id", "pathway_ref_id", name="uq_target_pathway"),
    )

    id = Column(String, primary_key=True, default=gen_id)
    tar_id = Column(String, ForeignKey("tcmsp_targets.tar_id"), nullable=False, index=True)
    pathway_ref_id = Column(String, ForeignKey("pathways.id"), nullable=False, index=True)
    source = Column(String, nullable=False, index=True)   # kegg / reactome
    via_symbol = Column(String, nullable=True)            # 靠哪個基因符號連上的
    via_accession = Column(String, nullable=True)         # 對應的 UniProt accession
    created_at = Column(DateTime, default=datetime.utcnow)
