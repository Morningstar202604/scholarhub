"""RLS isolation tests — must run against real PostgreSQL.

The main test suite uses SQLite in-memory (which has no Row Level
Security), so ScholarHUB's two-layer isolation claim is verified only
at the application-filter layer there. This file verifies the RLS layer
against a real PostgreSQL instance.

Connection URLs:

* ``SCHOLARHUB_DATABASE_URL`` — the app (restricted) role. Must be a
  non-superuser, non-table-owner role so RLS is actually enforced.
* ``SCHOLARHUB_RLS_ADMIN_URL`` — an admin/superuser role used for DDL
  (CREATE SCHEMA / CREATE ROLE / GRANT). Falls back to
  ``SCHOLARHUB_DATABASE_URL`` when unset (CI runs both as the same
  superuser role on a dedicated Postgres 17 service container).

Skipped automatically when ``SCHOLARHUB_DATABASE_URL`` does not
point to PostgreSQL.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Connection setup
# ---------------------------------------------------------------------------

DB_URL = os.environ.get("SCHOLARHUB_DATABASE_URL", "")
if not DB_URL.startswith("postgresql"):
    pytest.skip(
        "RLS tests require PostgreSQL; set SCHOLARHUB_DATABASE_URL=postgresql+asyncpg://...",
        allow_module_level=True,
    )

# Admin URL: used for DDL (CREATE ROLE/SCHEMA/TABLE/POLICY/GRANT).
# Falls back to DB_URL when unset (CI typically runs the whole suite
# as a single superuser role on a fresh Postgres service).
ADMIN_URL = os.environ.get("SCHOLARHUB_RLS_ADMIN_URL", DB_URL)

_RLS_SCHEMA = "scholarhub_rls_test"
_RLS_ROLE = "scholarhub_rls_test_role"
_RLS_ROLE_PW = "scholarhub_rls_test_pw"


def _swap_user(url: str, user: str, password: str) -> str:
    """Return ``url`` with the user/password swapped, host/port/db intact."""
    p = urlparse(url)
    return f"postgresql+asyncpg://{user}:{password}@{p.hostname or 'localhost'}:{p.port or 5432}/{p.path.lstrip('/')}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def rls_role():
    """Create + tear down the dedicated non-superuser RLS test role.

    Requires the admin URL (a role with CREATEROLE privilege) to be
    resolvable. Runs once per module.
    """
    admin_engine = create_async_engine(ADMIN_URL, echo=False)
    async with admin_engine.begin() as conn:
        await conn.exec_driver_sql(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_RLS_ROLE}') THEN "
            f"CREATE ROLE {_RLS_ROLE} LOGIN PASSWORD '{_RLS_ROLE_PW}' "
            f"NOSUPERUSER NOCREATEDB NOCREATEROLE; "
            f"ELSE "
            f"ALTER ROLE {_RLS_ROLE} LOGIN PASSWORD '{_RLS_ROLE_PW}' "
            f"NOSUPERUSER NOCREATEDB NOCREATEROLE; "
            f"END IF; END $$"
        )
    yield _RLS_ROLE, _RLS_ROLE_PW
    # Teardown: drop the role. The schema is dropped by the pg_engine
    # fixture's teardown (function scope, runs after this module-scoped
    # fixture's yield but before module exit). REVOKE on a possibly
    # already-dropped schema is harmless, so use DROP ROLE which
    # cascades the grants.
    async with admin_engine.begin() as conn:
        await conn.exec_driver_sql(f"DROP ROLE IF EXISTS {_RLS_ROLE};")
    await admin_engine.dispose()


@pytest.fixture
async def pg_engine(rls_role):
    """Per-test engine pair: admin engine for DDL + seed, RLS-role engine
    for the experiments.

    Function scope (not module) because ``asyncpg`` binds a connection
    to the event loop that created it, and pytest-asyncio gives each
    test its own loop. The schema is created and dropped per test;
    the DDL cost is negligible for a 4-test file.

    The experiments run under the dedicated non-superuser ``rls_role``
    so RLS is actually enforced — superusers and table owners bypass
    RLS in PostgreSQL regardless of FORCE.
    """
    role, pw = rls_role
    # DDL engine (admin): used to create the schema, tables, policies,
    # grants, and seed data (the admin role can bypass RLS on writes).
    admin_engine = create_async_engine(ADMIN_URL, echo=False)
    # Experiment engine (RLS role): used for the SELECT assertions where
    # RLS must filter rows.
    rls_engine = create_async_engine(
        _swap_user(DB_URL, role, pw), echo=False
    )

    async with admin_engine.begin() as conn:
        await conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {_RLS_SCHEMA} CASCADE")
        await conn.exec_driver_sql(f"CREATE SCHEMA {_RLS_SCHEMA}")
        await conn.exec_driver_sql(
            f"""
            CREATE TABLE {_RLS_SCHEMA}.tenants (
                id UUID PRIMARY KEY,
                slug VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(255),
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL
            )
            """
        )
        await conn.exec_driver_sql(
            f"""
            CREATE TABLE {_RLS_SCHEMA}.resources (
                id SERIAL PRIMARY KEY,
                tenant_id UUID NOT NULL,
                doi VARCHAR(255),
                title VARCHAR(500) NOT NULL,
                type VARCHAR(50) NOT NULL,
                year INTEGER,
                discipline VARCHAR(100),
                subdiscipline VARCHAR(100),
                publisher VARCHAR(255),
                external_url VARCHAR(500),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL
            )
            """
        )
        await conn.exec_driver_sql(
            f"""
            CREATE TABLE {_RLS_SCHEMA}.reading_list_items (
                id SERIAL PRIMARY KEY,
                tenant_id UUID NOT NULL,
                reading_list_id INTEGER NOT NULL,
                resource_id INTEGER NOT NULL,
                added_at TIMESTAMP WITH TIME ZONE NOT NULL
            )
            """
        )
        # RLS policies: FORCE so the table owner is also subject to RLS
        # (the RLS role is neither the owner nor a superuser, so FORCE
        # is a safety net; the experiment still works without it).
        for stmt in (
            f"ALTER TABLE {_RLS_SCHEMA}.resources ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {_RLS_SCHEMA}.resources FORCE ROW LEVEL SECURITY",
            f"ALTER TABLE {_RLS_SCHEMA}.reading_list_items ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {_RLS_SCHEMA}.reading_list_items FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY rls_resources ON {_RLS_SCHEMA}.resources "
            f"USING (tenant_id::text = current_setting('app.current_tenant_id', true))",
            f"CREATE POLICY rls_rli ON {_RLS_SCHEMA}.reading_list_items "
            f"USING (tenant_id::text = current_setting('app.current_tenant_id', true))",
            f"GRANT USAGE ON SCHEMA {_RLS_SCHEMA} TO {role}",
            f"GRANT SELECT ON {_RLS_SCHEMA}.resources TO {role}",
            f"GRANT SELECT ON {_RLS_SCHEMA}.reading_list_items TO {role}",
            f"GRANT SELECT ON {_RLS_SCHEMA}.tenants TO {role}",
        ):
            await conn.execute(text(stmt))

    yield {"admin": admin_engine, "rls": rls_engine}

    async with admin_engine.begin() as conn:
        await conn.exec_driver_sql(f"DROP SCHEMA IF EXISTS {_RLS_SCHEMA} CASCADE")
    await admin_engine.dispose()
    await rls_engine.dispose()


@pytest.fixture(autouse=True)
async def _no_cross_contamination(pg_engine):
    """No-op; kept for clarity that each test is fully isolated."""
    yield


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_as_admin(
    admin_engine,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed two tenants + 5 resources per tenant via the admin engine.

    The admin role (owner / superuser) can bypass RLS on writes, so
    seeding must go through it; the RLS role only has SELECT.
    Returns the two tenant UUIDs so experiments can reference them.
    """
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    async with admin_engine.begin() as conn:
        for tid, slug, name in (
            (tenant_a, "tenant-a", "Tenant A"),
            (tenant_b, "tenant-b", "Tenant B"),
        ):
            await conn.execute(
                text(
                    f"INSERT INTO {_RLS_SCHEMA}.tenants "
                    "(id, slug, name, is_active, created_at, updated_at) "
                    "VALUES (:id, :slug, :name, true, now(), now())"
                ),
                {"id": tid, "slug": slug, "name": name},
            )
        for i in range(5):
            for tid, prefix in ((tenant_a, "a"), (tenant_b, "b")):
                await conn.execute(
                    text(
                        f"INSERT INTO {_RLS_SCHEMA}.resources "
                        "(tenant_id, doi, title, type, year, discipline, subdiscipline, "
                        " publisher, external_url, created_at, updated_at) "
                        "VALUES (:tid, :doi, :title, 'article', 2024, 'cs', 'ml', "
                        " 'pub', NULL, now(), now())"
                    ),
                    {
                        "tid": tid,
                        "doi": f"10.1000/{prefix}-{i}",
                        "title": f"Tenant {prefix.upper()} resource {i}",
                    },
                )
    return tenant_a, tenant_b


def _rls_session(rls_engine):
    """Return an AsyncSession bound to the RLS-role engine."""
    return async_sessionmaker(
        rls_engine, class_=AsyncSession, expire_on_commit=False
    )()


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_experiment_a_own_tenant_returns_all_rows(pg_engine):
    """Experiment A: user A queries own resources with RLS enabled.

    The app filter is correct (WHERE tenant_id = A) and RLS is enabled.
    Expected: all 5 of A's rows returned. RLS does not interfere with
    legitimate same-tenant queries.
    """
    tenant_a, _ = await _seed_as_admin(pg_engine["admin"])
    session = _rls_session(pg_engine["rls"])
    await session.execute(
        text(f"SELECT set_config('app.current_tenant_id', '{tenant_a}', true)")
    )
    result = await session.execute(
        text(f"SELECT count(*) FROM {_RLS_SCHEMA}.resources WHERE tenant_id = :tid"),
        {"tid": tenant_a},
    )
    count = result.scalar_one()
    await session.commit()
    assert count == 5, f"expected 5 own-tenant rows, got {count}"


@pytest.mark.asyncio
async def test_experiment_b_rls_catches_cross_tenant_leak(pg_engine):
    """Experiment B: deliberately flawed filter + RLS enabled → 0 leak.

    The app filter is *missing* the tenant_id WHERE clause (simulating a
    developer bug), but RLS is enabled. The query asks for tenant B's
    resources while the RLS context is tenant A. RLS should deny every
    row of tenant B, returning 0.

    This is the critical experiment proving the two-layer defense.
    """
    tenant_a, tenant_b = await _seed_as_admin(pg_engine["admin"])
    session = _rls_session(pg_engine["rls"])
    await session.execute(
        text(f"SELECT set_config('app.current_tenant_id', '{tenant_a}', true)")
    )
    result = await session.execute(
        text(
            f"SELECT count(*) FROM {_RLS_SCHEMA}.resources "
            "WHERE tenant_id = :tid_b"
        ),
        {"tid_b": tenant_b},
    )
    count = result.scalar_one()
    await session.commit()
    assert count == 0, (
        f"RLS FAILED: cross-tenant leak detected — "
        f"tenant A context saw {count} of tenant B's rows"
    )


@pytest.mark.asyncio
async def test_experiment_c_disabling_rls_causes_leak(pg_engine):
    """Experiment C: same flawed filter + RLS disabled → leak confirmed.

    Same query as Experiment B, but RLS is fully disabled on
    ``resources`` (DISABLE ROW LEVEL SECURITY turns off the layer for
    all roles). Without the RLS layer the flawed filter returns tenant
    B's rows to tenant A's context — demonstrating that RLS is the
    layer providing the protection in Experiment B.
    """
    tenant_a, tenant_b = await _seed_as_admin(pg_engine["admin"])
    # Fully disable RLS on the table (via the admin engine).
    async with pg_engine["admin"].begin() as admin_conn:
        await admin_conn.execute(
            text(f"ALTER TABLE {_RLS_SCHEMA}.resources DISABLE ROW LEVEL SECURITY")
        )

    session = _rls_session(pg_engine["rls"])
    await session.execute(
        text(f"SELECT set_config('app.current_tenant_id', '{tenant_a}', true)")
    )
    result = await session.execute(
        text(f"SELECT count(*) FROM {_RLS_SCHEMA}.resources WHERE tenant_id = :tid_b"),
        {"tid_b": tenant_b},
    )
    count = result.scalar_one()
    await session.commit()
    assert count == 5, (
        f"Expected leak of 5 rows with RLS disabled, got {count}. "
        "If this returns 0, the test setup is wrong."
    )
    # Restore RLS for subsequent tests.
    async with pg_engine["admin"].begin() as admin_conn2:
        await admin_conn2.execute(
            text(f"ALTER TABLE {_RLS_SCHEMA}.resources ENABLE ROW LEVEL SECURITY")
        )
        await admin_conn2.execute(
            text(f"ALTER TABLE {_RLS_SCHEMA}.resources FORCE ROW LEVEL SECURITY")
        )


@pytest.mark.asyncio
async def test_rls_default_deny_when_no_context_set(pg_engine):
    """Default-deny: when no app.current_tenant_id is set, RLS returns 0 rows.

    ``current_setting('app.current_tenant_id', true)`` returns NULL when
    the setting is absent (the ``true`` arg = missing_ok). NULL never
    equals a non-null tenant_id, so RLS denies all rows. This is the
    fail-closed behavior that prevents data leaks if middleware fails
    to set the context.
    """
    await _seed_as_admin(pg_engine["admin"])
    session = _rls_session(pg_engine["rls"])
    # Do NOT set app.current_tenant_id — simulates middleware failure.
    # No local GUC is set in this transaction, so the RLS policy's
    # ``current_setting('app.current_tenant_id', true)`` returns NULL
    # and every row is denied.
    result = await session.execute(
        text(f"SELECT count(*) FROM {_RLS_SCHEMA}.resources")
    )
    count = result.scalar_one()
    await session.commit()
    assert count == 0, (
        f"Default-deny failed: RLS returned {count} rows when no "
        "tenant context was set. This is a fail-open vulnerability."
    )
