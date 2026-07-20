"""Email verification column on users

Revision ID: 008_email_verification
Revises: 007_library_module
Create Date: 2026-07-13 02:30:00

Adds ``users.is_email_verified`` (NOT NULL, default False). Existing
rows back-fill to False, which matches the previous implicit state
("no user has verified email").
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_email_verification"
down_revision: str | None = "007_library_module"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_email_verified")
