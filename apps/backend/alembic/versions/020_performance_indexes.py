"""Add performance indexes to ``resources``.

Why this revision exists
------------------------
The catalog listing / facet / search paths repeatedly filter or sort by
``tenant_id`` + ``created_at`` (default order), and by
``(tenant_id, type, created_at DESC)`` for "latest papers" pages. The
single-column indexes added by the original schema cover none of these
compound shapes, so every request does a seq scan + Python-side sort.

On top of that, full-text-ish ``ILIKE`` on ``title`` / ``abstract`` falls
back to seq scans on large catalogs; a GIN trigram index (pg_trgm)
resolves that.

What changes
------------
* ``ix_resources_tenant_created`` — composite ``(tenant_id, created_at DESC)``
* ``ix_resources_tenant_type_created`` — composite
  ``(tenant_id, type, created_at DESC)``
* ``ix_resources_title_trgm`` — GIN trigram on ``title`` (PostgreSQL only)
* ``ix_resources_abstract_trgm`` — GIN trigram on ``abstract``

The GIN trigram indexes are PostgreSQL-only (SQLite / dev environments
skip them — ILIKE still works, just with a seq scan).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020_performance_indexes"
down_revision: str | None = "019_doi_schema_drift"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    """True when running against a PostgreSQL database."""
    try:
        return inspect(op.get_bind()).dialect.name == "postgresql"
    except Exception:
        # get_bind may raise if no DB is connected (e.g. offline mode);
        # default to PostgreSQL since these indexes are most useful there.
        return True


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_resources_tenant_created
        ON resources (tenant_id, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_resources_tenant_type_created
        ON resources (tenant_id, type, created_at DESC);
        """
    )

    if _is_postgresql():
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_resources_title_trgm
            ON resources USING gin (title gin_trgm_ops);
            """
        )
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_resources_abstract_trgm
            ON resources USING gin (abstract gin_trgm_ops);
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_resources_tenant_type_created;")
    op.execute("DROP INDEX IF EXISTS ix_resources_tenant_created;")

    if _is_postgresql():
        op.execute("DROP INDEX IF EXISTS ix_resources_abstract_trgm;")
        op.execute("DROP INDEX IF EXISTS ix_resources_title_trgm;")
