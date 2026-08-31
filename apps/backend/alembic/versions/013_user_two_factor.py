"""users: add TOTP two-factor auth columns

Revision ID: 013_user_two_factor
Revises: 012_submission_versions
Create Date: 2026-07-30 12:00:00

Adds three columns to ``users``:

- ``two_factor_enabled`` (bool, NOT NULL, default false) — 2FA only
  takes effect once the user has confirmed a valid code during setup.
- ``two_factor_secret`` (varchar(64), nullable) — base32 TOTP secret.
  Plaintext by TOTP necessity (server must compute the same HMAC the
  authenticator app does); see app/core/twofactor.py.
- ``two_factor_recovery_codes`` (jsonb, nullable) — SHA-256 digests of
  the still-unused single-use recovery codes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "013_user_two_factor"
down_revision: str | None = "012_submission_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "users"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "two_factor_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column("two_factor_secret", sa.String(length=64), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "two_factor_recovery_codes",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "two_factor_recovery_codes")
    op.drop_column(_TABLE, "two_factor_secret")
    op.drop_column(_TABLE, "two_factor_enabled")
