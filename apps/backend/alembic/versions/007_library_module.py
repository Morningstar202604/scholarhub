"""Library module: reading_lists + reading_list_items

Revision ID: 007_library_module
Revises: 006_follows_module
Create Date: 2026-07-13 00:06:00

Creates the library module's two tables:

- ``reading_lists`` — (tenant, user, name). Tenant-scoped with RLS.
  The (tenant, user, name) tuple is unique so a user can't create two
  lists with the same name.

- ``reading_list_items`` — (list, resource). The (list_id, resource_id)
  tuple is unique so adding the same resource twice is a no-op. Items
  inherit tenant isolation via the FK to ``reading_lists`` (which is
  RLS-protected) and the route-layer owner check; no ``tenant_id``
  column here, so RLS is not enabled on this table.

``resource_id`` is an ``Integer`` FK → ``resources.id`` (the catalog
PK), used instead of business-id strings for sort stability and FK
performance.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_library_module"
down_revision: str | None = "006_follows_module"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Only reading_lists is tenant-scoped; reading_list_items inherits
# isolation via the FK to reading_lists (RLS-protected) + owner check
# in the route layer. No tenant_id column → no RLS on items.
_RLS_TABLES = ["reading_lists"]


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
    # --- reading_lists ---
    op.create_table(
        "reading_lists",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "name",
            name="uq_reading_lists_tenant_user_name",
        ),
    )
    op.create_index("ix_reading_lists_tenant_id", "reading_lists", ["tenant_id"])
    op.create_index("ix_reading_lists_user_id", "reading_lists", ["user_id"])

    # --- reading_list_items ---
    op.create_table(
        "reading_list_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reading_list_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["reading_list_id"], ["reading_lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "reading_list_id",
            "resource_id",
            name="uq_reading_list_item_resource",
        ),
    )
    op.create_index(
        "ix_reading_list_items_reading_list_id",
        "reading_list_items",
        ["reading_list_id"],
    )
    op.create_index(
        "ix_reading_list_items_resource_id",
        "reading_list_items",
        ["resource_id"],
    )

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
    op.drop_index("ix_reading_list_items_resource_id", table_name="reading_list_items")
    op.drop_index("ix_reading_list_items_reading_list_id", table_name="reading_list_items")
    op.drop_table("reading_list_items")
    op.drop_index("ix_reading_lists_user_id", table_name="reading_lists")
    op.drop_index("ix_reading_lists_tenant_id", table_name="reading_lists")
    op.drop_table("reading_lists")
