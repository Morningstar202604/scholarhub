"""Modules endpoint — exposes which modules are loaded.

The frontend calls this at boot to know which UI route chunks to render.
Per-tenant enable/disable state lives in the ``module_states`` table and
is managed via ``POST /api/admin/modules/{name}``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_tenant_id
from app.core.db import get_db
from app.core.modules import registry
from app.models import ModuleState, User
from app.schemas import ModuleInfo

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get("", response_model=list[ModuleInfo])
async def list_modules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ModuleInfo]:
    """List all loaded modules with their per-tenant enabled state.

    A module counts as enabled unless the current tenant has an explicit
    ``module_states`` row with ``is_enabled = False`` (the admin API
    only writes rows on change, so the default is "on").
    """
    tenant_id = require_tenant_id()
    result = await db.execute(
        select(ModuleState.module_name, ModuleState.is_enabled).where(
            ModuleState.tenant_id == tenant_id
        )
    )
    state_by_module: dict[str, bool] = {row[0]: row[1] for row in result.all()}

    out: list[ModuleInfo] = []
    for meta in registry.all_metadata():
        name = meta["name"]
        out.append(
            ModuleInfo(
                name=name,
                version=meta["version"],
                description=meta.get("description", ""),
                enabled=state_by_module.get(name, True),
            )
        )
    return out


__all__ = ["router"]
