"""disciplines + subdisciplines for academic taxonomy

Revision ID: 015_discipline_ontology
Revises: 014_orcid_enrichment
Create Date: 2026-07-25 17:10:00

Adds the controlled-vocabulary ontology for academic disciplines:

- ``disciplines`` (per-tenant, unique by (tenant_id, slug)). Used
  by the catalog to validate the ``resources.discipline`` string
  against a known set during create / update.
- ``subdisciplines`` (per-tenant, FK to ``disciplines.id``). Used
  to validate ``resources.subdiscipline`` belongs to the chosen
  discipline.

We deliberately do NOT add a hard FK from ``resources`` to
``disciplines`` because legacy data may have strings that aren't
in the ontology yet (ingested before this migration). The
validation is enforced at the application layer
(``app.modules.catalog.onto``). New writes must reference an
existing discipline slug; otherwise the request fails with 422.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "015_discipline_ontology"
down_revision = "014_orcid_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "disciplines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_disciplines_tenant_slug"),
    )
    op.create_index("ix_disciplines_tenant_id", "disciplines", ["tenant_id"], unique=False)

    op.create_table(
        "subdisciplines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "discipline_id",
            sa.Integer(),
            sa.ForeignKey("disciplines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.UniqueConstraint("discipline_id", "slug", name="uq_subdisciplines_discipline_slug"),
    )
    op.create_index("ix_subdisciplines_tenant_id", "subdisciplines", ["tenant_id"], unique=False)
    op.create_index(
        "ix_subdisciplines_discipline_id",
        "subdisciplines",
        ["discipline_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_subdisciplines_discipline_id", table_name="subdisciplines")
    op.drop_index("ix_subdisciplines_tenant_id", table_name="subdisciplines")
    op.drop_table("subdisciplines")
    op.drop_index("ix_disciplines_tenant_id", table_name="disciplines")
    op.drop_table("disciplines")
