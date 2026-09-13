"""Performance index smoke tests — verify composite indexes exist in PG.

These tests run against a real PostgreSQL instance and assert that the
composite indexes created by migration ``020_performance_indexes`` are
present in the database catalog. The planner uses these indexes for the
hot list-endpoint query shapes; without them PostgreSQL falls back to
sequential scans that degrade as data grows.

Skipped automatically when ``SCHOLARHUB_DATABASE_URL`` does not point
to PostgreSQL.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# ---------------------------------------------------------------------------
# Connection setup
# ---------------------------------------------------------------------------

DB_URL = os.environ.get("SCHOLARHUB_DATABASE_URL", "")
if not DB_URL.startswith("postgresql"):
    pytest.skip(
        "Performance smoke tests require PostgreSQL; "
        "set SCHOLARHUB_DATABASE_URL=postgresql+asyncpg://...",
        allow_module_level=True,
    )

ADMIN_URL = os.environ.get("SCHOLARHUB_RLS_ADMIN_URL", DB_URL)


def _admin_engine() -> AsyncEngine:
    return create_async_engine(ADMIN_URL, echo=False)


async def _index_exists(conn: Any, index_name: str) -> bool:
    result = await conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": index_name},
    )
    return result.scalar() is not None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submissions_editor_index_exists() -> None:
    """ix_submissions_editor_list (tenant_id, status, submitted_at DESC, id)
    supports the editor dashboard list endpoint."""
    engine = _admin_engine()
    try:
        async with engine.connect() as conn:
            exists = await _index_exists(conn, "ix_submissions_editor_list")
            assert exists, (
                "ix_submissions_editor_list not found in the database. "
                "Run 'alembic upgrade head' first."
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_submissions_recent_index_exists() -> None:
    """ix_submissions_recent (tenant_id, submitted_at DESC, id) supports
    the 'all my submissions' list endpoint."""
    engine = _admin_engine()
    try:
        async with engine.connect() as conn:
            exists = await _index_exists(conn, "ix_submissions_recent")
            assert exists, (
                "ix_submissions_recent not found in the database. Run 'alembic upgrade head' first."
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reading_history_composite_index_exists() -> None:
    """ix_reading_history_composite (tenant_id, user_id, viewed_at DESC, id)
    supports the 'my recent reads' list endpoint."""
    engine = _admin_engine()
    try:
        async with engine.connect() as conn:
            exists = await _index_exists(conn, "ix_reading_history_composite")
            assert exists, (
                "ix_reading_history_composite not found in the database. "
                "Run 'alembic upgrade head' first."
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_review_assignment_inbox_index_exists() -> None:
    """ix_review_assignments_inbox (tenant_id, reviewer_id, status,
    invited_at DESC, id) supports the reviewer inbox endpoint."""
    engine = _admin_engine()
    try:
        async with engine.connect() as conn:
            exists = await _index_exists(conn, "ix_review_assignments_inbox")
            assert exists, (
                "ix_review_assignments_inbox not found in the database. "
                "Run 'alembic upgrade head' first."
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_audit_log_actor_user_index_exists() -> None:
    """ix_audit_logs_actor_user_id supports filtering audit logs by
    the acting user without a full table scan."""
    engine = _admin_engine()
    try:
        async with engine.connect() as conn:
            exists = await _index_exists(conn, "ix_audit_logs_actor_user_id")
            assert exists, (
                "ix_audit_logs_actor_user_id not found in the database. "
                "Run 'alembic upgrade head' first."
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_submission_version_creator_index_exists() -> None:
    """ix_submission_versions_created_by supports looking up versions by
    author without a full scan of the versions table."""
    engine = _admin_engine()
    try:
        async with engine.connect() as conn:
            exists = await _index_exists(conn, "ix_submission_versions_created_by")
            assert exists, (
                "ix_submission_versions_created_by not found in the database. "
                "Run 'alembic upgrade head' first."
            )
    finally:
        await engine.dispose()
