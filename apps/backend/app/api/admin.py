"""Admin endpoints: list users, enable/disable users, list audit logs,
manage role assignments.

All endpoints require ``is_admin=True``. Per-tenant scoping is enforced
both at the application layer (explicit ``tenant_id`` filter on every
query) and by RLS in production. An admin in tenant A cannot read
tenant B's data.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, require_tenant_id
from app.core.db import get_db
from app.models import AuditLog, Role, User, UserRole
from app.schemas import RoleAssign, UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])

# Allowlist of assignable role names; mirrors Role.name values. Admin
# privilege is governed by User.is_admin, not by role membership.
ASSIGNABLE_ROLES = {"reviewer", "editor", "section_editor", "author", "reader"}


async def _user_with_roles(db: AsyncSession, user: User) -> UserResponse:
    """Build a UserResponse and populate its role-name list for the current tenant."""
    result = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user.id,
            UserRole.tenant_id == user.tenant_id,
            Role.tenant_id == user.tenant_id,
        )
    )
    role_names = sorted({r for r in result.scalars() if r})
    resp = UserResponse.model_validate(user)
    resp.roles = role_names
    return resp


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[UserResponse]:
    """List all users in the current tenant, including their role names."""
    tenant_id = require_tenant_id()
    result = await db.execute(
        select(User)
        .where(User.tenant_id == tenant_id)
        .order_by(User.id.desc())
        .limit(limit)
        .offset(offset)
    )
    users = result.scalars().all()
    return [await _user_with_roles(db, u) for u in users]


@router.patch("/users/{user_id}/active", response_model=UserResponse)
async def set_user_active(
    user_id: int,
    is_active: bool,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> UserResponse:
    """Enable or disable a user. Disabling yourself is refused.

    When disabling, bump both token_version AND refresh_token_version
    so the disabled user's outstanding tokens (access + refresh) become
    invalid immediately, not just on next login.
    """
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own active state from this endpoint",
        )
    tenant_id = require_tenant_id()
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    previous = user.is_active
    user.is_active = is_active
    if not is_active:
        # Disable invalidates every token we've ever handed out so the
        # user can't keep using a still-valid access/refresh token.
        user.token_version += 1
        user.refresh_token_version += 1
    # Audit trail: record who flipped whose active flag, in the same
    # transaction so the log row never exists without the change.
    db.add(
        AuditLog(
            tenant_id=current_admin.tenant_id,
            actor_user_id=current_admin.id,
            action="user.set_active",
            target_type="user",
            target_id=str(user.id),
            payload={"field": "is_active", "old": previous, "new": is_active},
        )
    )
    await db.commit()
    await db.refresh(user)
    return await _user_with_roles(db, user)


async def _get_or_create_role(
    db: AsyncSession, tenant_id: UUID, role_name: str
) -> Role:
    """Get or create a role row (name is unique per tenant)."""
    role = (
        await db.execute(
            select(Role).where(
                Role.tenant_id == tenant_id,
                Role.name == role_name,
            )
        )
    ).scalar_one_or_none()
    if role is not None:
        return role
    role = Role(tenant_id=tenant_id, name=role_name)
    db.add(role)
    await db.flush()
    return role


@router.post(
    "/users/{user_id}/roles",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_role(
    user_id: int,
    body: RoleAssign,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> UserResponse:
    """Assign a role to a user (idempotent per tenant: returns the current state if already assigned)."""
    if body.role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{body.role}' is not assignable",
        )
    tenant_id = require_tenant_id()
    user = (
        await db.execute(
            select(User).where(
                User.id == user_id,
                User.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    role = await _get_or_create_role(db, tenant_id, body.role)
    # Idempotent: if already assigned, return without re-inserting.
    existing = (
        await db.execute(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role_id == role.id,
                UserRole.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            UserRole(
                tenant_id=tenant_id,
                user_id=user.id,
                role_id=role.id,
            )
        )
        db.add(
            AuditLog(
                tenant_id=current_admin.tenant_id,
                actor_user_id=current_admin.id,
                action="user.assign_role",
                target_type="user",
                target_id=str(user.id),
                payload={"role": body.role},
            )
        )
        await db.commit()
    await db.refresh(user)
    return await _user_with_roles(db, user)


@router.delete(
    "/users/{user_id}/roles/{role_name}",
    response_model=UserResponse,
)
async def revoke_role(
    user_id: int,
    role_name: str,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> UserResponse:
    """Revoke a role from a user (returns 404 when absent, so silent success never misleads the frontend)."""
    tenant_id = require_tenant_id()
    if role_name not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{role_name}' is not revocable via this endpoint",
        )
    user = (
        await db.execute(
            select(User).where(
                User.id == user_id,
                User.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    role = (
        await db.execute(
            select(Role).where(
                Role.tenant_id == tenant_id,
                Role.name == role_name,
            )
        )
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_name}' not found in this tenant",
        )
    link = (
        await db.execute(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role_id == role.id,
                UserRole.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User does not have this role",
        )
    await db.delete(link)
    db.add(
        AuditLog(
            tenant_id=current_admin.tenant_id,
            actor_user_id=current_admin.id,
            action="user.revoke_role",
            target_type="user",
            target_id=str(user.id),
            payload={"role": role_name},
        )
    )
    await db.commit()
    await db.refresh(user)
    return await _user_with_roles(db, user)


@router.get("/audit-logs", response_model=list[dict[str, Any]])
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    """List recent audit log entries for the current tenant (newest first)."""
    tenant_id = require_tenant_id()
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": log.id,
            "tenant_id": str(log.tenant_id) if log.tenant_id else None,
            "actor_user_id": log.actor_user_id,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "payload": log.payload,
            "created_at": log.created_at.isoformat(),
        }
        for log in result.scalars()
    ]
