"""Follows module — author follow + discipline subscription.

Implements the ``author_follows`` + ``discipline_subscriptions`` flow
in a module-shaped home.

Design choices:

- Tenant-scoped (``tenant_id`` + RLS).
- Author follows key on the author NAME (string), not a separate
  ``authors`` table. The catalog module's design comment explicitly
  defers the structured ``Author`` (ORCID/affiliation) table to a
  future phase; the primary author storage on main is the JSON
  ``authors`` list[str] column on ``resources``. Following a string
  name matches that model and avoids forcing a cross-module FK to a
  table that does not exist yet.
- No rate limiting (consistent with notifications — adding a cross-
  cuttingting middleware is a separate concern).
- The notification fan-out (``notify_followers_of_new_resource``)
  is intentionally not wired back here yet. The follows module ships
  the follow/subscribe + listing endpoints; the submission review
  path will call ``notifications.services.create()`` in a follow-up
  patch to fan out to followers when a new catalog Resource is
  materialized from an approved submission. This keeps each module
  self-contained.
"""

from __future__ import annotations

from app.core.modules import ModuleManifest, registry

# Importing this package registers AuthorFollow + DisciplineSubscription
# with the shared core Base.metadata so Alembic and tests see them.
from app.modules.follows import models  # noqa: F401
from app.modules.follows.routes import router

registry.register(
    ModuleManifest(
        name="follows",
        version="0.1.0",
        description="Author follow + discipline subscription.",
        dependencies=frozenset(),
        router=router,
    )
)
