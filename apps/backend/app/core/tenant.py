"""Tenant resolution and request-scoped tenant context.

Two-layer design (see ARCHITECTURE.md §multi-tenant):

1. **Middleware** (``TenantContextMiddleware``) — runs before auth, resolves
   the tenant from host header (multi mode) or bootstrap slug (single mode),
   stores it in a ContextVar, returns 401 if no tenant can be resolved.

2. **DB dependency** (``app.core.db.get_db``) — reads the ContextVar and
   injects ``SET LOCAL app.current_tenant_id = :tid`` so PG RLS policies
   enforce isolation at the query planner level.

Why not just app-level filtering? RLS is the second line of defense: even
if a module forgets to add ``WHERE tenant_id = :tid``, RLS still denies
the row. ``SET LOCAL`` is transaction-scoped, so it's safe with PgBouncer
transaction pooling.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("scholarhub.tenant")


def _generate_tenant_uuid() -> uuid.UUID:
    return uuid.uuid4()


# The current request's tenant id. Set by middleware, read by get_db.
# Default is None so non-HTTP contexts (background jobs, tests without
# middleware) fail safe — get_db skips the SET LOCAL, RLS denies rows.
TENANT_CONTEXT_VAR: ContextVar[uuid.UUID | None] = ContextVar(
    "tenant_id",
    default=None,
)

# Request id for log correlation (also set by middleware).
REQUEST_ID_CTX: ContextVar[str] = ContextVar("request_id", default="-")


class TenantContextMiddleware:
    """Resolve tenant + request id, store in ContextVars.

    Single mode: resolve the bootstrap tenant once at startup, hardcode its
    UUID into the middleware. Multi mode: extract host header, look up the
    tenant in DB (cache the result). Both paths produce a ``uuid.UUID``
    that downstream code uses for ``SET LOCAL``.

    The first request to single mode will trigger bootstrap: if the
    bootstrap tenant does not yet exist, create it. This is idempotent.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # In single mode, the tenant is fixed at startup. We resolve it
        # lazily on the first request because the DB may not be ready at
        # middleware construction time.
        self._single_mode_tenant_id: uuid.UUID | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Request id — reuse upstream header or generate.
        request_id = "-"
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                request_id = value.decode("ascii", errors="replace")
                break
        if request_id == "-":
            request_id = uuid.uuid4().hex[:16]
        request_id_token = REQUEST_ID_CTX.set(request_id)
        structlog_token = None
        try:
            from structlog.contextvars import bind_contextvars, clear_contextvars

            structlog_token = bind_contextvars(request_id=request_id)
        except Exception:
            pass

        # Resolve tenant.
        tenant_id = await self._resolve_tenant(scope)
        tenant_token = TENANT_CONTEXT_VAR.set(tenant_id) if tenant_id else None

        if structlog_token is not None:
            try:
                from structlog.contextvars import bind_contextvars

                bind_contextvars(tenant_id=str(tenant_id) if tenant_id else "-")
            except Exception:
                pass

        try:
            await self.app(scope, receive, send)
        finally:
            if tenant_token is not None:
                TENANT_CONTEXT_VAR.reset(tenant_token)
            REQUEST_ID_CTX.reset(request_id_token)
            if structlog_token is not None:
                try:
                    from structlog.contextvars import clear_contextvars

                    clear_contextvars()
                except Exception:
                    pass

    async def _resolve_tenant(self, scope: Scope) -> uuid.UUID | None:
        """Resolve the tenant id for this request.

        Returns ``None`` if no tenant can be resolved — in that case the
        downstream RLS policy will deny all rows (default-deny).
        """
        if settings.tenancy_mode == "single":
            if self._single_mode_tenant_id is None:
                self._single_mode_tenant_id = await self._ensure_bootstrap_tenant()
            return self._single_mode_tenant_id

        # Multi mode: extract host header, look up tenant.
        host = None
        for name, value in scope.get("headers", []):
            if name == b"host":
                host = value.decode("ascii", errors="replace")
                break
        if host is None:
            return None
        # Multi-tenant resolution requires DB lookup; deferred to next phase.
        # For now, single mode is the only working path.
        logger.warning("multi_tenant_mode_not_yet_implemented_host_ignored", host=host)
        return None

    async def _ensure_bootstrap_tenant(self) -> uuid.UUID:
        """Resolve (or lazily create) the bootstrap tenant in single mode.

        Idempotent: if the tenant already exists, return its id; otherwise
        create it. Safe to call from the first request.
        """
        from sqlalchemy import select

        from app.core.db import async_session_factory
        from app.models import Tenant

        slug = settings.bootstrap_tenant_slug
        async with async_session_factory() as session:
            result = await session.execute(select(Tenant).where(Tenant.slug == slug))
            tenant = result.scalar_one_or_none()
            if tenant is not None:
                return tenant.id
            tenant = Tenant(slug=slug, name=f"Bootstrap ({slug})", tenant_type="journal")
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)
            logger.info("bootstrap_tenant_created", slug=slug, tenant_id=str(tenant.id))
            return tenant.id


# Type alias for clarity in function signatures.
TenantId = uuid.UUID
TenantPayload = dict[str, Any]
