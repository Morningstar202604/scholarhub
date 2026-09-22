"""Add users.totp_last_used_counter for TOTP replay protection

Revision ID: 022_user_totp_last_used_counter
Revises: 021_unify_two_factor
Create Date: 2026-09-22 14:45:00

Closes the T2 white-box finding H-1: ``core/totp.verify_totp`` accepts a
``last_counter`` argument for replay protection (reject any counter at or
below the highest one already consumed), and its docstring promises the
protection works — but no caller ever passed the argument and no column stored
the value, so the same 6-digit code could be replayed within its 30-second
window on both 2FA completion paths (``/auth/login/2fa`` and
``/auth/2fa/authenticate``).

The column is nullable: ``NULL`` means "no code accepted yet" (fresh
enrolment or accounts enrolled before this migration). The API layer
seeds it on the first successful verification after this deploy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022_user_totp_last_used_counter"
down_revision: str | None = "021_unify_two_factor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USERS_TABLE = "users"


def upgrade() -> None:
    op.add_column(
        _USERS_TABLE,
        sa.Column("totp_last_used_counter", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(_USERS_TABLE, "totp_last_used_counter")
