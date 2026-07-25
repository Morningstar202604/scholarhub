"""Follows module: author_follows + discipline_subscriptions

Revision ID: 006_follows_module
Revises: 005_notifications_module
Create Date: 2026-07-13 00:05:00

Creates the follows module's two tables:

- ``author_follows`` — (tenant, user, author_name string). Keyed on
  the author NAME, not a structured Author entity, because the catalog
  module defers the structured Author (ORCID/affiliation) table to a
  future phase. Following a string matches catalog's primary author
  storage (JSON list[str] on resources) and lets the follow
  relationship exist independently of any catalog record.

- ``discipline_subscriptions`` — (tenant, user, discipline slug). The
  slug is a free-form string; the catalog module owns the canonical
  list, but follows does not enforce it cross-module to avoid coupling
  module enablement.

Both tables carry a UniqueConstraint on (tenant_id, user_id, <target>)
so the relationship is idempotent at the DB level — re-following the
same author is a no-op rather than a 409.

Tenant-scoped with RLS mirroring the base spine strategy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_follows_module"
down_revision: str | None = "005_notifications_module"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FOLLOWS_TABLES = ["author_follows", "discipline_subscriptions"]


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
    # --- author_follows ---
    op.create_table(
        "author_follows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("author_name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "author_name",
            name="uq_author_follows_tenant_user_author",
        ),
    )
    op.create_index("ix_author_follows_tenant_id", "author_follows", ["tenant_id"])
    op.create_index("ix_author_follows_user_id", "author_follows", ["user_id"])
    op.create_index("ix_author_follows_author_name", "author_follows", ["author_name"])

    # --- discipline_subscriptions ---
    op.create_table(
        "discipline_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("discipline", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "discipline",
            name="uq_discipline_subscriptions_tenant_user_discipline",
        ),
    )
    op.create_index(
        "ix_discipline_subscriptions_tenant_id",
        "discipline_subscriptions",
        ["tenant_id"],
    )
    op.create_index(
        "ix_discipline_subscriptions_user_id",
        "discipline_subscriptions",
        ["user_id"],
    )
    op.create_index(
        "ix_discipline_subscriptions_discipline",
        "discipline_subscriptions",
        ["discipline"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _FOLLOWS_TABLES:
            _enable_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _FOLLOWS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_discipline_subscriptions_discipline", table_name="discipline_subscriptions")
    op.drop_index("ix_discipline_subscriptions_user_id", table_name="discipline_subscriptions")
    op.drop_index("ix_discipline_subscriptions_tenant_id", table_name="discipline_subscriptions")
    op.drop_table("discipline_subscriptions")
    op.drop_index("ix_author_follows_author_name", table_name="author_follows")
    op.drop_index("ix_author_follows_user_id", table_name="author_follows")
    op.drop_index("ix_author_follows_tenant_id", table_name="author_follows")
    op.drop_table("author_follows")
