"""reading_list_items: add tenant_id column + RLS

Revision ID: 009_reading_list_items_tenant_id
Revises: 008_email_verification
Create Date: 2026-07-14 00:01:00

Previously ``reading_list_items`` had no ``tenant_id`` column — isolation
was inherited via the FK to ``reading_lists`` plus a route-layer owner
check. This meant:

1. PostgreSQL RLS could not protect the table directly (no tenant_id
   column for the policy to compare against ``current_setting``).
2. Direct queries (admin endpoints, background jobs, ad-hoc scripts)
   without RLS would leak rows across tenants.

This migration adds ``tenant_id`` (non-null, indexed, FK to tenants),
back-fills it from the parent ``reading_lists.tenant_id``, then enables
RLS with the standard tenant_isolation policy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_reading_list_items_tenant_id"
down_revision: str | None = "008_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "reading_list_items"
_RLS_TABLES = [_TABLE]


def _enable_rls(table: str) -> None:
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
    # Add the column as nullable first so the back-fill can populate it.
    op.add_column(
        _TABLE,
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Back-fill from the parent reading_lists row.
    op.execute(
        f"""
        UPDATE {_TABLE} AS item
        SET tenant_id = rl.tenant_id
        FROM reading_lists AS rl
        WHERE item.reading_list_id = rl.id;
        """
    )

    # Now make it NOT NULL — every row must have a tenant.
    op.alter_column(
        _TABLE, "tenant_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False
    )

    op.create_index(f"ix_{_TABLE}_tenant_id", _TABLE, ["tenant_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _RLS_TABLES:
            _enable_rls(table)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _RLS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    op.drop_index(f"ix_{_TABLE}_tenant_id", table_name=_TABLE)
    op.drop_column(_TABLE, "tenant_id")
