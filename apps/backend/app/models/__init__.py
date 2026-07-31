"""ORM models for the base spine.

All models inherit from ``Base`` (defined here). Domain-specific tables
(submissions, publications, etc.) live in module packages under
``app.modules.<name>.models`` and contribute their own ``Base.metadata``
via the module registry.

Every multi-tenant table MUST carry ``tenant_id`` (UUID, non-null, indexed)
and rely on PostgreSQL RLS for isolation. See ARCHITECTURE.md §Tenancy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.time import utcnow

# JSONB falls back to JSON on SQLite so in-memory tests can run.
JSONBVariant = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    """Declarative base for the core models. Modules declare their own
    ``Base`` subclasses; the registry merges their metadata into the
    Alembic target_metadata (see alembic/env.py).
    """

    pass


class Tenant(Base):
    """A tenant = one journal/press/server/etc. on the platform.

    In single mode, exactly one row exists (created lazily on first
    startup). In multi mode, one row per tenant. All domain tables carry
    ``tenant_id`` referencing this table.
    """

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    # Type enables future expansion: 'journal' | 'press' | 'server' | 'institution'.
    tenant_type: Mapped[str] = mapped_column(String(32), default="journal")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Arbitrary key/value settings — replaces OJS-style ``*_settings`` tables.
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONBVariant, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    users: Mapped[list[User]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class User(Base):
    """A platform user. Belongs to one tenant; role assignments are M:N.

    ``token_version`` is bumped on logout/password change to
    invalidate all outstanding access tokens.

    ``refresh_token_version`` is a separate counter bumped on each
    ``/auth/refresh`` call. It invalidates only the consumed refresh
    token (and any other refresh tokens issued before this refresh) —
    access tokens and the user's other devices are not affected.
    This is OAuth2-standard refresh token rotation: a stolen refresh
    token becomes useless the moment the legitimate holder refreshes.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        UniqueConstraint("tenant_id", "username", name="uq_users_tenant_username"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Independent from token_version so refresh rotation does not log out
    # every device the way logout / password change do.
    refresh_token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # --- TOTP two-factor auth (opt-in per user) ---
    # The secret is written during setup but 2FA only takes effect once
    # ``two_factor_enabled`` flips True — i.e. after the user has proven
    # they can produce a valid code from it. Stored in plaintext by TOTP
    # necessity; see app/core/twofactor.py for the rationale.
    two_factor_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    two_factor_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # SHA-256 digests of the still-unused single-use recovery codes.
    two_factor_recovery_codes: Mapped[list[str] | None] = mapped_column(
        JSONBVariant, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    tenant: Mapped[Tenant] = relationship(back_populates="users")
    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Role(Base):
    """Pre-defined role labels per tenant. Roles are NOT user-defined yet —
    a fixed enum is enough for the base spine.

    The base ships with: editor / section_editor / author / reviewer /
    reader. Modules may add their own roles by inserting rows here.
    """

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    assignments: Mapped[list[UserRole]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class UserRole(Base):
    """M:N between User and Role, scoped per tenant.

    Both User and Role already carry tenant_id; this junction table
    repeats it for RLS coverage and easier per-tenant queries.
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "role_id", name="uq_user_roles_tenant_user_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="assignments")


class ModuleState(Base):
    """Tracks per-tenant module enable/disable state.

    The Python ``ENABLED_MODULES`` list controls which modules are
    *loaded* at the process level (code available). This table tracks
    which modules are *enabled* per tenant (admin can turn modules off
    for a specific tenant without redeploying).
    """

    __tablename__ = "module_states"
    __table_args__ = (
        UniqueConstraint("tenant_id", "module_name", name="uq_module_states_tenant_module"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONBVariant, nullable=True)
    enabled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class AuditLog(Base):
    """Immutable record of destructive operations (user delete, role change,
    module enable/disable, schema migration).

    Append-only: never UPDATE or DELETE rows. The admin UI exposes this
    read-only; the cleanup policy is a separate operational concern.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(128))
    # Arbitrary structured payload (before/after/diff).
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONBVariant, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
        index=True,
    )


__all__ = [
    "AuditLog",
    "Base",
    "ModuleState",
    "Role",
    "Tenant",
    "User",
    "UserRole",
]
