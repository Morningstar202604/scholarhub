"""users: add TOTP 2FA columns

Revision ID: 012_user_totp
Revises: 011_review_module
Create Date: 2026-07-24 12:30:00

Adds three columns to ``users`` for TOTP (RFC 6238) 2FA:

- ``totp_secret_encrypted`` (String(512), NULL): the user's TOTP secret
  encrypted at rest with Fernet using ``SCHOLARHUB_FERNET_KEY``. NULL
  means 2FA has never been set up.
- ``totp_enabled_at`` (DateTime(timezone=True), NULL): the timestamp
  the user successfully verified their first code, marking the feature
  as "live". The setup endpoint emits a secret without setting this
  column; only the verify-setup endpoint flips it.
- ``totp_backup_codes_hashed`` (String(2048), NULL): a JSON array of
  bcrypt hashes for the one-time backup codes shown at enrollment /
  regeneration. Cleartext codes are shown exactly once and never
  persisted; the column is wiped on regenerate.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_user_totp"
down_revision: str | None = "011_review_module"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "users"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("totp_secret_encrypted", sa.String(length=512), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "totp_enabled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "totp_backup_codes_hashed",
            sa.String(length=2048),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "totp_backup_codes_hashed")
    op.drop_column(_TABLE, "totp_enabled_at")
    op.drop_column(_TABLE, "totp_secret_encrypted")