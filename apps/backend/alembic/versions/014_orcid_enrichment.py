"""users.orcid + resources.authors_meta for academic attribution

Revision ID: 014_orcid_enrichment
Revises: 013_user_deleted_at
Create Date: 2026-07-25 16:56:00

Adds:
- ``users.orcid`` (String(20), NULL, indexed). The ORCID iD in its
  canonical 16-digit form, e.g. ``0000-0002-1825-0097``. Optional.
- ``resources.authors_meta`` (JSON, NULL). Optional list of
  per-author enrichment objects: ``[{name, orcid?, affiliation?,
  email?}, ...]``. Parallel to the existing ``authors`` JSON column
  (which stays the display source of truth).

Both columns are nullable and unconstrained so existing rows /
imports keep working. Format validation lives in the API layer
where it can return helpful 4xx responses.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "014_orcid_enrichment"
down_revision = "013_user_deleted_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("orcid", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_users_tenant_orcid",
        "users",
        ["tenant_id", "orcid"],
        unique=False,
    )
    op.add_column(
        "resources",
        sa.Column("authors_meta", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("resources", "authors_meta")
    op.drop_index("ix_users_tenant_orcid", table_name="users")
    op.drop_column("users", "orcid")
