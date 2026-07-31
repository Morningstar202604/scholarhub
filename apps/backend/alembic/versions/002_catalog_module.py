"""Catalog module: resources + resource_stats

Revision ID: 002_catalog_module
Revises: 001_initial_schema_with_rls
Create Date: 2026-07-13 00:01:00

Creates the catalog module's two tables:

- ``resources`` — core bibliographic record (int PK + tenant_id + slug +
  title/authors/year/venue/discipline/tags/abstract/doi + journal metadata).
  No citation cache column and no view/download counters here; those
  live in ``resource_stats``.
- ``resource_stats`` — per-resource counters (views, downloads,
  citation count) split out to avoid write hotspots on the catalog row.

Both tables are tenant-scoped and get PostgreSQL RLS policies mirroring
the base spine's strategy (ENABLE + FORCE + tenant_isolation policy).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_catalog_module"
down_revision: str | None = "001_initial_schema_with_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATALOG_TABLES = ["resources", "resource_stats"]


def _enable_rls(table: str) -> None:
    """Enable + force RLS, then attach the tenant_isolation policy."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
        FOR ALL
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
        """
    )


def upgrade() -> None:
    # --- resources ---
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("venue", sa.Text(), nullable=True),
        sa.Column("discipline", sa.String(length=100), nullable=False),
        sa.Column("subdiscipline", sa.String(length=100), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("preview", sa.Text(), nullable=False),
        sa.Column("download_url", sa.String(length=500), nullable=True),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("doi", sa.String(length=200), nullable=True),
        # Journal metadata
        sa.Column("volume", sa.String(length=50), nullable=True),
        sa.Column("issue", sa.String(length=50), nullable=True),
        sa.Column("pages", sa.String(length=50), nullable=True),
        sa.Column("issn", sa.String(length=20), nullable=True),
        sa.Column("isbn", sa.String(length=20), nullable=True),
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column(
            "publication_status",
            sa.String(length=20),
            nullable=False,
            server_default="published",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_resources_tenant_slug"),
    )
    op.create_index("ix_resources_tenant_id", "resources", ["tenant_id"])
    op.create_index("ix_resources_type", "resources", ["type"])
    op.create_index("ix_resources_year", "resources", ["year"])
    op.create_index("ix_resources_venue", "resources", ["venue"])
    op.create_index("ix_resources_discipline", "resources", ["discipline"])
    op.create_index("ix_resources_subdiscipline", "resources", ["subdiscipline"])
    op.create_index("ix_resources_doi", "resources", ["doi"])

    # --- resource_stats ---
    op.create_table(
        "resource_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("citations", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "resource_id", name="uq_resource_stats_tenant_resource"),
    )
    op.create_index("ix_resource_stats_tenant_id", "resource_stats", ["tenant_id"])
    op.create_index("ix_resource_stats_resource_id", "resource_stats", ["resource_id"])

    # --- RLS policies (PostgreSQL only; no-op on SQLite in tests) ---
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _CATALOG_TABLES:
            _enable_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _CATALOG_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_resource_stats_resource_id", table_name="resource_stats")
    op.drop_index("ix_resource_stats_tenant_id", table_name="resource_stats")
    op.drop_table("resource_stats")
    op.drop_index("ix_resources_doi", table_name="resources")
    op.drop_index("ix_resources_subdiscipline", table_name="resources")
    op.drop_index("ix_resources_discipline", table_name="resources")
    op.drop_index("ix_resources_venue", table_name="resources")
    op.drop_index("ix_resources_year", table_name="resources")
    op.drop_index("ix_resources_type", table_name="resources")
    op.drop_index("ix_resources_tenant_id", table_name="resources")
    op.drop_table("resources")
