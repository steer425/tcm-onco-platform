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
