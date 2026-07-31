"""Reader module: file_assets + reading_history

Revision ID: 003_reader_module
Revises: 002_catalog_module
Create Date: 2026-07-13 00:02:00

Creates the reader module's two tables:

- ``file_assets`` — PDF host metadata (filename / mime / size / storage
  path / sha256 / uploader). No FK back to ``resources``: that link is
  owned by the catalog module and may be added by a future catalog-side
  migration as ``resources.pdf_file_id``.
- ``reading_history`` — one row per (tenant, user, resource) combining
  the access log (viewed_at + visit_count) with cross-device progress
  (page / progress_percent / duration_sec / last_read_at / completed).
  The unique constraint on (tenant_id, user_id, resource_id) makes the
  upsert path a single-row lookup; the IntegrityError retry in
  ``PUT /progress`` handles concurrent inserts.

Both tables are tenant-scoped and get PostgreSQL RLS policies mirroring
the base spine's strategy (ENABLE + FORCE + tenant_isolation policy).
``file_assets.uploaded_by`` carries no tenant_id filter (it is a SET NULL
FK to users) but the row's tenant_id controls visibility.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_reader_module"
down_revision: str | None = "002_catalog_module"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_READER_TABLES = ["file_assets", "reading_history"]


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
    # --- file_assets ---
    op.create_table(
        "file_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("storage_backend", sa.String(length=20), nullable=False, server_default="local"),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        # Per-tenant dedup space: same sha256 in two tenants is allowed.
        sa.UniqueConstraint("tenant_id", "sha256", name="uq_file_assets_tenant_sha256"),
    )
    op.create_index("ix_file_assets_tenant_id", "file_assets", ["tenant_id"])
    op.create_index("ix_file_assets_sha256", "file_assets", ["sha256"])
    op.create_index("ix_file_assets_uploaded_by", "file_assets", ["uploaded_by"])

    # --- reading_history ---
    op.create_table(
        "reading_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column(
            "viewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("visit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "resource_id",
            name="uq_reading_history_tenant_user_resource",
        ),
    )
    op.create_index("ix_reading_history_tenant_id", "reading_history", ["tenant_id"])
    op.create_index("ix_reading_history_user_id", "reading_history", ["user_id"])
    op.create_index("ix_reading_history_resource_id", "reading_history", ["resource_id"])
    op.create_index(
        "ix_reading_history_viewed_at",
        "reading_history",
        ["viewed_at"],
    )

    # --- RLS policies (PostgreSQL only; no-op on SQLite in tests) ---
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _READER_TABLES:
            _enable_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _READER_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_reading_history_viewed_at", table_name="reading_history")
    op.drop_index("ix_reading_history_resource_id", table_name="reading_history")
    op.drop_index("ix_reading_history_user_id", table_name="reading_history")
    op.drop_index("ix_reading_history_tenant_id", table_name="reading_history")
    op.drop_table("reading_history")
    op.drop_index("ix_file_assets_uploaded_by", table_name="file_assets")
    op.drop_index("ix_file_assets_sha256", table_name="file_assets")
    op.drop_index("ix_file_assets_tenant_id", table_name="file_assets")
    op.drop_table("file_assets")
