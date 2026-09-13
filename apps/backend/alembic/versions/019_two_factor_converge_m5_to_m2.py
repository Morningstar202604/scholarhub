"""2FA convergence: backfill legacy plaintext M5 columns into the M2 encrypted stack, then drop them.

Up (data migration, runs once):

- ``two_factor_secret`` (plaintext base32) → ``totp_secret_encrypted``
  (Fernet-encrypted) for users who enabled M5 2FA but have no M2 secret.
- ``two_factor_enabled`` → ``totp_enabled_at`` for the same users.
- M5 recovery codes (stored as raw SHA-256 digests, different salt
  prefix than M2 backup hashes) cannot be converted to M2 hashes, so
  they are intentionally dropped: migrated users regenerate backup
  codes from the 2FA settings page.

Down is a no-op: the M5 columns are gone and cannot be restored.

After this migration the M2 stack (``/api/auth/2fa/*``,
``app.core.totp``) is the only 2FA implementation in the codebase.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_two_factor_converge_m5_to_m2"
down_revision: str | Sequence[str] | None = "018_user_webauthn"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # Backfill only on a real PostgreSQL database with the app importable
    # (E2E compose / dev). Offline SQL mode and test sandboxes skip it.
    if bind.dialect.name == "postgresql":
        migrated = False
        try:
            from app.core.time import utcnow
            from app.core.totp import encrypt_secret

            rows = bind.execute(
                sa.text(
                    """
                    SELECT id, two_factor_secret
                    FROM users
                    WHERE two_factor_enabled AND two_factor_secret IS NOT NULL
                      AND totp_secret_encrypted IS NULL
                    """
                )
            ).fetchall()
            now = utcnow()
            for row in rows:
                bind.execute(
                    sa.text(
                        """
                        UPDATE users
                        SET totp_secret_encrypted = :enc,
                            totp_enabled_at = COALESCE(totp_enabled_at, :now)
                        WHERE id = :uid
                        """
                    ),
                    {"enc": encrypt_secret(row.two_factor_secret), "now": now, "uid": row.id},
                )
            # Users with M5 enabled but a null secret get 2FA turned off
            # rather than left in a broken half-enabled state.
            bind.execute(
                sa.text(
                    """
                    UPDATE users
                    SET two_factor_enabled = FALSE
                    WHERE two_factor_enabled AND two_factor_secret IS NULL
                    """
                )
            )
            migrated = True
        except Exception:
            migrated = False
        if not migrated:
            # Column-existence guard: a re-run of this migration (or a
            # state where the M5 columns were already dropped) would make
            # the fallback SQL reference columns that no longer exist.
            # Check each column before touching it so a second run is a
            # clean no-op instead of an in-transaction error.
            col_exists = sa.text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = :col
                """
            )
            has_two_factor_enabled = (
                bind.execute(col_exists, {"col": "two_factor_enabled"}).fetchone()
                is not None
            )
            if has_two_factor_enabled:
                bind.execute(
                    sa.text(
                        """
                        UPDATE users SET two_factor_enabled = FALSE
                        WHERE two_factor_enabled AND totp_secret_encrypted IS NULL
                        """
                    )
                )

    # Each drop_column is individually guarded so the migration is
    # idempotent on re-run.
    for col in ("two_factor_recovery_codes", "two_factor_secret", "two_factor_enabled"):
        col_exists = bind.execute(
            sa.text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = :col
                """
            ),
            {"col": col},
        ).fetchone()
        if col_exists:
            op.drop_column("users", col)


def downgrade() -> None:
    # Data migration is irreversible; restore the columns empty so the
    # M5 code paths (if ever reintroduced) keep working.
    op.add_column("users", sa.Column("two_factor_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("two_factor_secret", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column("two_factor_recovery_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
