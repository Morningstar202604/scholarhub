"""Unify two-factor onto the encrypted totp_* columns and drop dead resource_stats

Revision ID: 021_unify_two_factor
Revises: 020_performance_indexes
Create Date: 2026-09-21 23:45:00

This migration closes two review findings:

1. **Two-factor dual tracking.** Migration 012 created the encrypted
   ``totp_*`` column group (``totp_secret_encrypted`` / ``totp_enabled_at``
   / ``totp_backup_codes_hashed``) while migration 013 added a second,
   plaintext group (``two_factor_enabled`` / ``two_factor_secret`` /
   ``two_factor_recovery_codes``). Both stayed live: the login gate read
   only ``two_factor_enabled`` while the admin gate read only
   ``totp_enabled_at``, so whichever path a user enrolled through, some
   gate disagreed — 2FA silently ineffective on one path, admins locked
   out on the other. All code now uses the encrypted ``totp_*`` group,
   so the plaintext group is dropped here.

   This project is still pre-release, but the instance may already have
   real enrolments, so the upgrade carries them over instead of silently
   turning 2FA off: for every row with ``two_factor_enabled`` set, the
   plaintext secret is re-encrypted with Fernet into
   ``totp_secret_encrypted`` and ``totp_enabled_at`` is stamped, which
   keeps the account protected and still challenged at login. Legacy
   *recovery codes* are not portable (013 hashed them as
   ``sha256(code)`` while ``core/totp.py`` verifies
   ``sha256("scholarhub:backup:" + code)``), so affected users regenerate
   them from the 2FA settings page.

2. **Dead ``resource_stats`` table.** No endpoint ever wrote or read a
   row (the promised view/download counters were never implemented), and
   the ORM model has been removed. Dropping the table keeps the schema
   honest instead of advertising tracking that does not exist.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021_unify_two_factor"
down_revision: str | None = "020_performance_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USERS_TABLE = "users"


def upgrade() -> None:
    # --- 1. carry legacy plaintext enrolments over to the encrypted group -
    # 必须在 DROP 之前执行：否则线上已经开了 2FA 的账号会被静默降级成"未开启"。
    _carry_over_legacy_enrolments()

    # --- 2. drop the legacy plaintext two-factor column group -------------
    op.drop_column(_USERS_TABLE, "two_factor_recovery_codes")
    op.drop_column(_USERS_TABLE, "two_factor_secret")
    op.drop_column(_USERS_TABLE, "two_factor_enabled")

    # --- 3. drop the never-used resource_stats table ----------------------
    op.drop_index("ix_resource_stats_resource_id", table_name="resource_stats")
    op.drop_index("ix_resource_stats_tenant_id", table_name="resource_stats")
    op.drop_table("resource_stats")


def _carry_over_legacy_enrolments() -> None:
    """Re-encrypt legacy plaintext TOTP secrets into ``totp_secret_encrypted``.

    只有 ``two_factor_enabled`` 为真且有密钥的行会被搬运；搬运后在
    ``totp_enabled_at`` 打上时间戳——登录闸门与管理员闸门都读这一列，所以
    这些账号继续受 2FA 保护，而不是被"悄悄关掉"。

    取密钥走应用自身的 ``settings.fernet_key``（非 test 环境里它是启动必需项），
    加密格式复用 ``core/totp.encrypt_secret``，保证与运行期同构。
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, two_factor_enabled, two_factor_secret FROM users")
    ).fetchall()
    pending = [(r[0], r[2]) for r in rows if r[1] and r[2]]
    if not pending:
        return

    # 延迟导入：迁移期才需要 app 侧配置与加密实现。
    from datetime import datetime

    from app.core.totp import encrypt_secret

    stamp = datetime.now(UTC)
    for user_id, secret in pending:
        bind.execute(
            sa.text(
                "UPDATE users SET totp_secret_encrypted = :tok, "
                "totp_enabled_at = :ts WHERE id = :uid"
            ),
            {"tok": encrypt_secret(secret), "ts": stamp, "uid": user_id},
        )


def downgrade() -> None:
    # --- 1. recreate resource_stats exactly as migration 002 defined it ---
    op.create_table(
        "resource_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("citations", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "resource_id", name="uq_resource_stats_tenant_resource"),
    )
    op.create_index("ix_resource_stats_tenant_id", "resource_stats", ["tenant_id"])
    op.create_index("ix_resource_stats_resource_id", "resource_stats", ["resource_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE resource_stats ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE resource_stats FORCE ROW LEVEL SECURITY;")
        op.execute(
            "CREATE POLICY tenant_isolation ON resource_stats "
            "USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid) "
            "WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);"
        )

    # --- 2. restore the legacy plaintext two-factor column group ----------
    op.add_column(
        _USERS_TABLE,
        sa.Column(
            "two_factor_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        _USERS_TABLE,
        sa.Column("two_factor_secret", sa.String(length=64), nullable=True),
    )
    op.add_column(
        _USERS_TABLE,
        sa.Column(
            "two_factor_recovery_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # --- 3. carry enrolments back so a rollback doesn't drop 2FA ----------
    _carry_back_to_legacy_columns()


def _carry_back_to_legacy_columns() -> None:
    """把加密列组里的报名数据还原成旧的明文列（downgrade 对称性）。

    旧恢复码无法还原（见模块 docstring：两边哈希方案不同），但密钥与开关能回去，
    回滚后这些账号仍然是 2FA 账号。
    """
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, totp_secret_encrypted FROM users")).fetchall()
    pending = [(r[0], r[1]) for r in rows if r[1]]
    if not pending:
        return

    from app.core.totp import decrypt_secret

    for user_id, token in pending:
        bind.execute(
            sa.text(
                "UPDATE users SET two_factor_enabled = :on, "
                "two_factor_secret = :sec WHERE id = :uid"
            ),
            {"on": True, "sec": decrypt_secret(token), "uid": user_id},
        )
