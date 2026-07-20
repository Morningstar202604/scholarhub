"""Notifications module — in-app notification stream.

Implements the ``notifications`` flow in a module-shaped home.

Design choices:

- Tenant-scoped (``tenant_id`` + RLS).
- The cross-module fan-out (firing notifications from inside the
  submission review handler) is intentionally NOT wired back here yet.
  The notification model + endpoints + an internal ``create()``
  helper ship now; the submission module's review path will be updated
  to call ``notifications.create()`` in a follow-up patch (this keeps
  the submission commit self-contained and avoids forcing both modules
  to ship in lockstep).
- No rate limiting in this module — the base spine does not wire one
  in yet, and adding it is a separate concern (cross-cutting
  middleware, not module-local).
"""

from __future__ import annotations

from app.core.modules import ModuleManifest, registry

# Importing this package registers Notification with the shared core
# Base.metadata so Alembic and tests see it alongside the core tables.
from app.modules.notifications import models  # noqa: F401
from app.modules.notifications.routes import router

registry.register(
    ModuleManifest(
        name="notifications",
        version="0.1.0",
        description="In-app notifications stream.",
        dependencies=frozenset(),
        router=router,
    )
)
