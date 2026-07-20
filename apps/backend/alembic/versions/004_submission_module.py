"""Submission module: submissions table

Revision ID: 004_submission_module
Revises: 003_reader_module
Create Date: 2026-07-13 00:03:00

Creates the submission module's single table:

- ``submissions`` — author-submitted bibliographic records awaiting
  editor review. Fields mirror catalog ``resources`` so an approval can
  materialize a Resource with no field reshuffling. The ``resource_id``
  column is set on approval to point at the catalog Resource created
  from (or linked to) the submission.

The submitter + reviewer FKs point at ``users.id`` (core); the resource
FK points at ``catalog.resources.id``. Cross-module FKs resolve because
the submission model inherits from the core ``Base`` (ARCHITECTURE.md
"All modules share the tenant's PostgreSQL database").

Tenant-scoped with RLS mirroring the base spine strategy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_submission_module"
down_revision: str | None = "003_reader_module"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUBMISSION_TABLES = ["submissions"]


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
    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
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
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_submissions_tenant_id", "submissions", ["tenant_id"])
    op.create_index("ix_submissions_submitted_by", "submissions", ["submitted_by"])
    op.create_index("ix_submissions_reviewed_by", "submissions", ["reviewed_by"])
    op.create_index("ix_submissions_resource_id", "submissions", ["resource_id"])
    op.create_index("ix_submissions_status", "submissions", ["status"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _SUBMISSION_TABLES:
            _enable_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _SUBMISSION_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_submissions_status", table_name="submissions")
    op.drop_index("ix_submissions_resource_id", table_name="submissions")
    op.drop_index("ix_submissions_reviewed_by", table_name="submissions")
    op.drop_index("ix_submissions_submitted_by", table_name="submissions")
    op.drop_index("ix_submissions_tenant_id", table_name="submissions")
    op.drop_table("submissions")
