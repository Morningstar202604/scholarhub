"""迁移 021 的数据搬运回归测试。

021 除了删列，还要把老的明文 2FA 报名数据（013 的 ``two_factor_*``）搬进加密列组
（012 的 ``totp_*``）。这条路径只在"库里已有老数据"时才会走到，而 CI 的 migrations
job 是全新建库跑 ``alembic upgrade head``，永远命中不到它——所以这里手工建一张最小
``users`` 表，直接把迁移里的搬运函数钉住。

（迁移本身是 PostgreSQL-only：JSONB 在其它方言下无法渲染，因此这里不跑整条 upgrade，
只验证"老报名 → 加密 + 打上启用时间戳"这段业务不变量。）
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.core.totp import decrypt_secret

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "021_unify_two_factor.py"
)


def _load_migration() -> ModuleType:
    """按路径加载迁移模块（alembic 的 version 文件不是包，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location("migration_021", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_users_table(engine: sa.Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    two_factor_enabled BOOLEAN NOT NULL DEFAULT 0,
                    two_factor_secret VARCHAR(64),
                    totp_secret_encrypted VARCHAR(512),
                    totp_enabled_at DATETIME
                )
                """
            )
        )


def test_legacy_enrolment_moves_to_encrypted_columns() -> None:
    """老路径开启过 2FA 的账号必须继续是 2FA 账号，而不是被静默关掉。"""
    engine = sa.create_engine("sqlite://")
    _make_users_table(engine)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users (id, two_factor_enabled, two_factor_secret) "
                "VALUES (1, 1, 'JBSWY3DPEHPK3PXP')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO users (id, two_factor_enabled, two_factor_secret) VALUES (2, 0, NULL)"
            )
        )

    migration = _load_migration()
    with engine.begin() as conn:
        # 让迁移里的 op.get_bind() 落到这条测试连接上。
        migration.op = Operations(MigrationContext.configure(conn))  # type: ignore[attr-defined]
        migration._carry_over_legacy_enrolments()  # type: ignore[attr-defined]
        rows = conn.execute(
            sa.text("SELECT id, totp_secret_encrypted, totp_enabled_at FROM users ORDER BY id")
        ).fetchall()

    # 账号 1：密钥以 Fernet 密文形式落库（运行期用 decrypt_secret 能读回来），
    # 并且打上启用时间戳——登录闸门与管理员闸门都读这一列。
    assert rows[0][1] is not None
    assert decrypt_secret(rows[0][1]) == "JBSWY3DPEHPK3PXP"
    assert rows[0][2] is not None

    # 账号 2：从未开启 2FA，保持未开启。
    assert rows[1][1] is None
    assert rows[1][2] is None


def test_carryover_is_a_noop_without_legacy_rows() -> None:
    """全新建库（没有老数据）时搬运必须静默跳过，不能报错。"""
    engine = sa.create_engine("sqlite://")
    _make_users_table(engine)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users (id, two_factor_enabled, two_factor_secret) VALUES (1, 1, NULL)"
            )
        )

    migration = _load_migration()
    with engine.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))  # type: ignore[attr-defined]
        migration._carry_over_legacy_enrolments()  # type: ignore[attr-defined]
        row = conn.execute(
            sa.text("SELECT totp_secret_encrypted, totp_enabled_at FROM users WHERE id = 1")
        ).fetchone()

    # 开关为真但密钥为空（历史脏数据）：不写半截状态。
    assert row[0] is None
    assert row[1] is None
