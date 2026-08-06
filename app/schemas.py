from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models import ApplicationStatus, BackupStatus, OAuthProvider, UserStatus


# ---------- Auth ----------

class LoginRequest(BaseModel):
    account: str
    password: str
    device_id: Optional[str] = None  # 前端可傳送裝置識別資訊（無法取得真實網卡編號）


class ApplyAccountRequest(BaseModel):
    account: str
    password: str
    notes: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    login_log_id: str


# ---------- User ----------

class UserCreate(BaseModel):
    account: str
    password: str
    role_ids: List[str] = []
    notes: Optional[str] = None


class UserUpdate(BaseModel):
    status: Optional[UserStatus] = None
    suspend_reason: Optional[str] = None
    notes: Optional[str] = None
    role_ids: Optional[List[str]] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    id: str
    account: str
    status: UserStatus
    suspend_reason: Optional[str]
    notes: Optional[str]
    role_names: List[str] = []
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Role ----------

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    notes: Optional[str] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None


class RoleOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    notes: Optional[str]
    is_system: bool
    user_count: int = 0

    class Config:
        from_attributes = True


# ---------- Feature / Permission matrix ----------

class FeatureCreate(BaseModel):
    code: str
    module: str
    name: str
    description: Optional[str] = None
    notes: Optional[str] = None
    nav_label: Optional[str] = None
    page_url: Optional[str] = None
    show_frontend: bool = False
    show_backend: bool = True
    sort_order: int = 0


class FeatureUpdate(BaseModel):
    module: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    nav_label: Optional[str] = None
    page_url: Optional[str] = None
    enabled: Optional[bool] = None
    show_frontend: Optional[bool] = None
    show_backend: Optional[bool] = None
    sort_order: Optional[int] = None


class FeatureOut(BaseModel):
    id: str
    code: str
    module: str
    name: str
    description: Optional[str]
    notes: Optional[str]
    enabled: bool
    show_frontend: bool
    show_backend: bool
    nav_label: Optional[str]
    page_url: Optional[str]
    sort_order: int

    class Config:
        from_attributes = True


class PermissionSet(BaseModel):
    feature_id: str
    can_view: bool = False
    can_execute: bool = False
    notes: Optional[str] = None
    # 以下為全站共用設定（不分角色），一併從權限矩陣視窗編輯，儲存時會同步更新到 Feature 本身
    enabled: Optional[bool] = None
    show_frontend: Optional[bool] = None
    show_backend: Optional[bool] = None
    nav_label: Optional[str] = None
    sort_order: Optional[int] = None


class RolePermissionBulkUpdate(BaseModel):
    role_id: str
    permissions: List[PermissionSet]


class RolePermissionOut(BaseModel):
    feature_id: str
    feature_code: str
    feature_name: str
    can_view: bool
    can_execute: bool
    notes: Optional[str]
    # 全站共用設定（顯示用，供權限矩陣視窗一併編輯）
    enabled: bool
    show_frontend: bool
    show_backend: bool
    nav_label: Optional[str]
    page_url: Optional[str]
    sort_order: int

    class Config:
        from_attributes = True


# ---------- Account application ----------

class ApplicationReview(BaseModel):
    approve: bool
    notes: Optional[str] = None


class ApplicationOut(BaseModel):
    id: str
    account: str
    status: ApplicationStatus
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- OAuth ----------

class OAuthLinkCreate(BaseModel):
    provider: OAuthProvider
    provider_user_id: str
    notes: Optional[str] = None


class OAuthAccountOut(BaseModel):
    id: str
    provider: OAuthProvider
    provider_user_id: str
    linked_at: datetime
    notes: Optional[str]

    class Config:
        from_attributes = True


# ---------- Audit log ----------

class AuditLogOut(BaseModel):
    id: str
    actor_account: Optional[str]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    detail: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogNoteUpdate(BaseModel):
    notes: str


# ---------- Backup job ----------

class BackupJobOut(BaseModel):
    id: str
    started_at: datetime
    finished_at: Optional[datetime]
    status: BackupStatus
    file_path: Optional[str]
    size_bytes: Optional[int]
    notes: Optional[str]

    class Config:
        from_attributes = True


class BackupJobNoteUpdate(BaseModel):
    notes: str


# ---------- 目標五：中藥行 / 評價 ----------

class PharmacyCreate(BaseModel):
    name: str
    address: str
    phone: Optional[str] = None
    business_hours: Optional[str] = None
    description: Optional[str] = None
    latitude: float
    longitude: float
    notes: Optional[str] = None


class PharmacyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    business_hours: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class PharmacyOut(BaseModel):
    id: str
    name: str
    address: str
    phone: Optional[str]
    business_hours: Optional[str]
    description: Optional[str]
    latitude: float
    longitude: float
    status: str
    notes: Optional[str]
    avg_rating: Optional[float] = None
    review_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class PharmacyReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


class PharmacyReviewUpdate(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = None


class PharmacyReviewNoteUpdate(BaseModel):
    notes: str


class PharmacyReviewOut(BaseModel):
    id: str
    pharmacy_id: str
    user_id: str
    account: Optional[str] = None
    rating: int
    comment: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Login log ----------

class LoginLogOut(BaseModel):
    id: str
    account: str
    ip_address: Optional[str]
    device_id: Optional[str]
    user_agent: Optional[str]
    login_at: datetime
    logout_at: Optional[datetime]
    duration_seconds: Optional[int]
    notes: Optional[str]

    class Config:
        from_attributes = True


class LoginLogNoteUpdate(BaseModel):
    notes: str


# ---------- 公告 ----------

class AnnouncementCreate(BaseModel):
    title: str
    content: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    notes: Optional[str] = None


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class AnnouncementFileOut(BaseModel):
    id: str
    filename: str
    content_type: Optional[str]
    file_size: Optional[int]
    uploaded_at: datetime

    class Config:
        from_attributes = True


class AnnouncementOut(BaseModel):
    id: str
    title: str
    content: Optional[str]
    start_at: datetime
    end_at: Optional[datetime]
    status: str
    notes: Optional[str]
    is_currently_visible: bool = False  # 依目前時間 + start_at/end_at + status 即時計算，於 router 內覆寫
    created_at: datetime
    files: List[AnnouncementFileOut] = []

    class Config:
        from_attributes = True


# ---------- 病患基本資料 / 就診紀錄 ----------

class PatientCreate(BaseModel):
    patient_id: str
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    name: str
    sex_code: Optional[str] = None
    birth_date: Optional[str] = None
    nationality_code: Optional[str] = None
    ethnicity_code: Optional[str] = None
    address: Optional[str] = None
    telephone: Optional[str] = None
    medical_record_no: Optional[str] = None
    notes: Optional[str] = None


class PatientUpdate(BaseModel):
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    name: Optional[str] = None
    sex_code: Optional[str] = None
    birth_date: Optional[str] = None
    nationality_code: Optional[str] = None
    ethnicity_code: Optional[str] = None
    address: Optional[str] = None
    telephone: Optional[str] = None
    medical_record_no: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class PatientOut(BaseModel):
    id: str
    patient_id: str
    id_type: Optional[str]
    id_number_masked: str = ""  # 遮罩後的證件號碼，例如 A12***678，於 router 內覆寫
    name: str
    sex_code: Optional[str]
    birth_date: Optional[str]
    nationality_code: Optional[str]
    ethnicity_code: Optional[str]
    address: Optional[str]
    telephone: Optional[str]
    medical_record_no: Optional[str]
    status: str
    notes: Optional[str]
    encounter_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class EncounterCreate(BaseModel):
    encounter_id: str
    patient_id: str  # Patient.id（內部 UUID，不是 patient_id 欄位）
    medical_institution: Optional[str] = None
    department: Optional[str] = None
    diagnosis_code: Optional[str] = None
    diagnosis_name: Optional[str] = None
    encounter_date: Optional[str] = None
    notes: Optional[str] = None


class EncounterUpdate(BaseModel):
    medical_institution: Optional[str] = None
    department: Optional[str] = None
    diagnosis_code: Optional[str] = None
    diagnosis_name: Optional[str] = None
    encounter_date: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class EncounterOut(BaseModel):
    id: str
    encounter_id: str
    patient_id: str
    medical_institution: Optional[str]
    department: Optional[str]
    diagnosis_code: Optional[str]
    diagnosis_name: Optional[str]
    encounter_date: Optional[str]
    status: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- 暗黑基因（癌症基因參考資料）----------

class DarkGeneCreate(BaseModel):
    hugo_symbol: str
    entrez_gene_id: Optional[str] = None
    grch37_isoform: Optional[str] = None
    grch37_refseq: Optional[str] = None
    grch38_isoform: Optional[str] = None
    grch38_refseq: Optional[str] = None
    gene_type: Optional[str] = None
    occurrence_count: Optional[int] = None
    oncokb_annotated: bool = False
    msk_impact: bool = False
    msk_heme: bool = False
    foundation_one: bool = False
    foundation_one_heme: bool = False
    vogelstein: bool = False
    cosmic_cgc: bool = False
    gene_aliases: Optional[str] = None
    notes: Optional[str] = None


class DarkGeneUpdate(BaseModel):
    entrez_gene_id: Optional[str] = None
    grch37_isoform: Optional[str] = None
    grch37_refseq: Optional[str] = None
    grch38_isoform: Optional[str] = None
    grch38_refseq: Optional[str] = None
    gene_type: Optional[str] = None
    occurrence_count: Optional[int] = None
    oncokb_annotated: Optional[bool] = None
    msk_impact: Optional[bool] = None
    msk_heme: Optional[bool] = None
    foundation_one: Optional[bool] = None
    foundation_one_heme: Optional[bool] = None
    vogelstein: Optional[bool] = None
    cosmic_cgc: Optional[bool] = None
    gene_aliases: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class DarkGeneOut(BaseModel):
    id: str
    hugo_symbol: str
    entrez_gene_id: Optional[str]
    grch37_isoform: Optional[str]
    grch37_refseq: Optional[str]
    grch38_isoform: Optional[str]
    grch38_refseq: Optional[str]
    gene_type: Optional[str]
    occurrence_count: Optional[int]
    oncokb_annotated: bool
    msk_impact: bool
    msk_heme: bool
    foundation_one: bool
    foundation_one_heme: bool
    vogelstein: bool
    cosmic_cgc: bool
    gene_aliases: Optional[str]
    status: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
