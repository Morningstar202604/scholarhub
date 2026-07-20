"""Submission module — author → editor → catalog workflow.

Implements the ``resource_submissions`` flow in a module-shaped home,
with these deliberate design choices:

- Tenant-scoped (``tenant_id`` + RLS).
- ``resource_id`` is an integer FK to ``catalog.resources.id``; the
  catalog module uses int PKs everywhere.
- The approval path always creates a catalog ``Resource`` from the
  submission payload. The catalog module exposes a clean admin POST
  endpoint that we call here, so the conversion logic lives where
  Resource creation belongs (catalog) — submission only orchestrates
  the flow.
- Notification + follower fan-out is intentionally dropped here.
  Notifications are a separate module (roadmap step 5); wiring it
  now would leak concerns across module boundaries.
"""

from __future__ import annotations

from app.core.modules import ModuleManifest, registry

# Importing this package registers Submission with the shared core
# Base.metadata, so Alembic and tests see it alongside the catalog tables
# without extra wiring.
from app.modules.submission import models  # noqa: F401
from app.modules.submission.routes import router

registry.register(
    ModuleManifest(
        name="submission",
        version="0.1.0",
        description="Author submission and editor review workflow.",
        dependencies=frozenset({"catalog"}),
        router=router,
    )
)
