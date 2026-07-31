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
    """對應各功能模組/頁面，例如 F0-2 角色管理頁面"""
    __tablename__ = "features"

    id = Column(String, primary_key=True, default=gen_id)
    code = Column(String, unique=True, nullable=False)   # e.g. F0-2
    module = Column(String, nullable=False)              # e.g. 目標零
    name = Column(String, nullable=False)                # e.g. 角色管理
    description = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

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
