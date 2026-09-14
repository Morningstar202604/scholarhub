"""Create the missing ``doi_registrations`` table and close schema drift.

Why this revision exists
------------------------
The test suite builds its schema with ``Base.metadata.create_all()`` on an
in-memory SQLite database. That means a table which is declared as a model
but never created by any revision stays invisible to CI: every test passes
while a production database migrated to ``head`` simply has no such table.

``doi_registrations`` was exactly that case — ``app.modules.doi.models``
declares it, no revision created it, so every DOI endpoint would have failed
at runtime with ``relation "doi_registrations" does not exist``.

Two smaller drifts are closed here as well:

* ``users.orcid`` is ``VARCHAR(20)`` in the database but ``String(200)`` in
  the model, so values accepted by the model could not be stored.
* ``reading_list_items.tenant_id`` never received its foreign key, so
  deleting a tenant left orphaned rows behind.

``doi_registrations`` also gets the same row level security treatment as the
other tenant-scoped tables; without it the table would be readable across
tenants and break the isolation guarantee the rest of the schema relies on.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_doi_schema_drift"
down_revision: str | None = "20d879058fa2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
        "doi_registrations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("doi", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("registered_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["registered_by"],
            ["users.id"],
            name=op.f("fk_doi_registrations_registered_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"],
            ["resources.id"],
            name=op.f("fk_doi_registrations_resource_id_resources"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_doi_registrations_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doi_registrations")),
    )
    op.create_index(
        op.f("ix_doi_registrations_doi"),
        "doi_registrations",
        ["doi"],
        unique=False,
    )
    op.create_index(
        op.f("ix_doi_registrations_registered_by"),
        "doi_registrations",
        ["registered_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_doi_registrations_resource_id"),
        "doi_registrations",
        ["resource_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_doi_registrations_tenant_id"),
        "doi_registrations",
        ["tenant_id"],
        unique=False,
    )
    _enable_rls("doi_registrations")

    # users.orcid: widen to match the model (String(200)).
    op.alter_column(
        "users",
        "orcid",
        existing_type=sa.VARCHAR(length=20),
        type_=sa.String(length=200),
        existing_nullable=True,
    )

    # reading_list_items.tenant_id: add the missing foreign key so tenant
    # deletion cascades instead of leaving orphan rows.
    op.create_foreign_key(
        "fk_reading_list_items_tenant_id_tenants",
        "reading_list_items",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_reading_list_items_tenant_id_tenants",
        "reading_list_items",
        type_="foreignkey",
    )

    op.alter_column(
        "users",
        "orcid",
        existing_type=sa.String(length=200),
        type_=sa.VARCHAR(length=20),
        existing_nullable=True,
    )

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON doi_registrations;")
    op.execute("ALTER TABLE doi_registrations DISABLE ROW LEVEL SECURITY;")
    op.drop_index(op.f("ix_doi_registrations_tenant_id"), table_name="doi_registrations")
    op.drop_index(op.f("ix_doi_registrations_resource_id"), table_name="doi_registrations")
    op.drop_index(op.f("ix_doi_registrations_registered_by"), table_name="doi_registrations")
    op.drop_index(op.f("ix_doi_registrations_doi"), table_name="doi_registrations")
    op.drop_table("doi_registrations")
