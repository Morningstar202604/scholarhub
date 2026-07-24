"""users: add deleted_at column for GDPR soft-delete

Revision ID: 013_user_deleted_at
Revises: 012_user_totp
Create Date: 2026-07-24 21:30:00

Adds ``deleted_at`` (DateTime(timezone=True), NULL, indexed) to
``users``. A non-NULL value means the user has self-deleted via
``DELETE /api/users/me`` and is in the 30-day grace window before a
scheduled hard-delete sweep purges the row. Indexes the column so
the sweep query (and admin UI filters) stay cheap.

This is the M5 GDPR hardening migration. We do NOT rename or
remove any existing columns; existing rows get ``deleted_at = NULL``
which is the default and means "account is alive".
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013_user_deleted_at"
down_revision: str | None = "012_user_totp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_deleted_at",
        "users",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_column("users", "deleted_at")