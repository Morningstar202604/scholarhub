"""users: add refresh_token_version column for token rotation

Revision ID: 010_user_refresh_token_version
Revises: 009_reading_list_items_tenant_id
Create Date: 2026-07-14 00:02:00

Adds ``refresh_token_version`` (int, NOT NULL, default 0) to ``users``.
Independent from ``token_version`` so refresh token rotation invalidates
only the consumed refresh token (and any older ones) without logging out
every device the way a ``token_version`` bump would.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_user_refresh_token_version"
down_revision: str | None = "009_reading_list_items_tenant_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "users"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "refresh_token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "refresh_token_version")
