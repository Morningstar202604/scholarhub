"""Pydantic schemas for the base spine API.

Auth + user + module + admin endpoints. Domain schemas (catalog,
submission, etc.) live in module packages.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


# --- Auth ---
class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    user_id: int
    username: str
    is_admin: bool


# --- Two-factor auth (TOTP) ---
class TwoFactorRequiredResponse(BaseModel):
    """Returned by /auth/login when the account has 2FA enabled.

    No access/refresh tokens yet — the client exchanges
    ``pending_token`` + a TOTP (or recovery) code at /auth/login/2fa.
    """

    two_factor_required: Literal[True] = True
    pending_token: str


class TwoFactorLoginRequest(BaseModel):
    pending_token: str = Field(min_length=1)
    # 6-digit TOTP or a xxxx-xxxx-xxxx recovery code
    code: str = Field(min_length=6, max_length=32)


class TwoFactorSetupResponse(BaseModel):
    """Secret + otpauth URI for the enrolment QR code. 2FA is NOT yet
    active — the user must confirm with a valid code via /2fa/enable."""

    secret: str
    otpauth_uri: str


class TwoFactorEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class TwoFactorEnableResponse(BaseModel):
    enabled: Literal[True] = True
    # Shown exactly once at enable time; only hashes are stored.
    recovery_codes: list[str]


class TwoFactorDisableRequest(BaseModel):
    # Require the account password so a hijacked session can't
    # silently strip the second factor.
    password: str = Field(min_length=1)


class TwoFactorStatusResponse(BaseModel):
    enabled: bool
    recovery_codes_remaining: int


# --- Email verification + password reset ---
class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


# --- User ---
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # 输出 schema 不再用 EmailStr：数据库里已存过的 email 视为合法。
    # 之前用 EmailStr 会导致 admin@scholarhub.local 这类保留 TLD 邮箱无法
    # 序列化（admin/users 直接 500），输出端做二次校验是反模式。
    email: str
    username: str
    is_active: bool
    is_admin: bool
    is_email_verified: bool
    created_at: datetime
    # 当前用户在本租户内被授予的角色名列表（如 ["reviewer", "editor"]）
    # 默认空列表：未填充时视为"无角色"，向后兼容旧调用点
    roles: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _do_not_lazy_load_roles(cls, data: Any) -> Any:
        """防止 from_attributes 触发 User.roles SQLAlchemy relationship lazy load。

        SQLAlchemy relationship 异步访问会抛 MissingGreenlet；这里拦截 ORM 实例
        并只取标量字段，让 roles 走默认空列表（admin 端点用 _user_with_roles 显式填充）。
        """
        # 用 duck typing 避免循环 import：检查是否为 SQLAlchemy ORM 实例
        if hasattr(data, "__dict__") and hasattr(data, "__table__") is False:
            # 不是 ORM 实例的常见情况：dict、关键字参数等直接返回
            if not hasattr(data, "_sa_instance_state"):
                return data
        if hasattr(data, "_sa_instance_state"):
            # ORM 实例：只取标量列，避免触发 relationship lazy load
            return {
                "id": data.id,
                "email": data.email,
                "username": data.username,
                "is_active": data.is_active,
                "is_admin": data.is_admin,
                "is_email_verified": data.is_email_verified,
                "created_at": data.created_at,
                # roles 不在此填：让默认空列表生效；admin 路径用 _user_with_roles 显式覆盖
            }
        return data


class RoleAssign(BaseModel):
    """Body for POST /admin/users/{id}/roles — assign a role to a user."""

    # 仅允许分配审稿相关角色；admin 角色由 is_admin 字段控制，不在此处
    role: Literal["reviewer", "editor", "section_editor", "author", "reader"]


class ReviewModeUpdate(BaseModel):
    """Body for PATCH /admin/settings/review-mode."""

    review_mode: Literal["single_blind", "double_blind"]


class ReviewModeResponse(BaseModel):
    review_mode: Literal["single_blind", "double_blind"]


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=100)
    is_active: bool | None = None


# --- Module ---
class ModuleInfo(BaseModel):
    name: str
    version: str
    description: str = ""


# --- Health ---
class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class HealthReadyResponse(BaseModel):
    status: Literal["ok", "error"]
    database: Literal["connected", "unavailable"]


# --- Tenant ---
class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    tenant_type: str
    is_active: bool
