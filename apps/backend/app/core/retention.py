"""Data-retention constants and helpers.

Values match the public privacy policy so the policy and the code
cannot drift apart silently. Operators run the cleanup jobs from
their scheduler of choice; we expose ``retention_cutoff`` so a
caller can compute the bound without hard-coding the policy in
multiple places.

Retention policy (mirrors ``/api/privacy``):

- Account PII: held until the user requests deletion; soft-deleted
  accounts are anonymised in place and hard-deleted after
  ``USER_DELETION_GRACE_DAYS`` days.
- Audit logs: ``AUDIT_LOG_RETENTION_DAYS`` days.
- Backups: 90 days (operational concern, not enforced in code).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

# 30-day window between soft delete and hard delete of the user row.
# Match the value advertised in /api/privacy.
USER_DELETION_GRACE_DAYS: int = 30

# Audit logs are retained for one year. After this window the row
# is purged by the operational cleanup job; the policy is exported
# via /api/privacy and reflected in any data-export request.
AUDIT_LOG_RETENTION_DAYS: int = 365


def audit_log_cutoff(now: datetime | None = None) -> datetime:
    """Return the timestamp at or below which audit log rows are
    eligible for hard-deletion."""
    moment = now if now is not None else datetime.now(UTC)
    return moment - timedelta(days=AUDIT_LOG_RETENTION_DAYS)


def user_hard_delete_cutoff(deleted_at: datetime, now: datetime | None = None) -> datetime:
    """Return the timestamp at or below which a soft-deleted user row
    is eligible for hard-deletion (i.e. ``deleted_at`` + grace)."""
    return deleted_at + timedelta(days=USER_DELETION_GRACE_DAYS)


async def run_retention_cleanup(db: Any) -> dict[str, object]:
    """Execute the retention policy: purge expired audit logs and
    hard-delete users whose soft-delete grace window has lapsed.

    Caller must own the session lifecycle (commit/rollback). All deletes
    run inside the caller's transaction with the tenant GUC armed, so
    RLS restricts the blast radius to the current tenant. FK cascades
    (``ondelete``) handle the module-side rows at the database layer.
    """
    from sqlalchemy import delete, func, select

    from app.models import AuditLog, User

    now = datetime.now(UTC)

    audit_result = await db.execute(
        delete(AuditLog).where(AuditLog.created_at <= audit_log_cutoff(now))
    )

    # Expired soft-deleted users: deleted_at + grace <= now.
    expiring = (
        select(User.id)
        .where(User.deleted_at.is_not(None))
        .where(User.deleted_at <= now - timedelta(days=USER_DELETION_GRACE_DAYS))
        .scalar_subquery()
    )
    user_result = await db.execute(delete(User).where(User.id.in_(expiring)))

    # Integrity guard: count the users that SHOULD have expired but did
    # not (e.g. FKs that were not cascading). Surface it instead of
    # silently claiming the policy ran.
    leftover: int = await db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.deleted_at.is_not(None))
        .where(User.deleted_at <= now - timedelta(days=USER_DELETION_GRACE_DAYS))
    )

    return {
        "audit_logs_deleted": int(audit_result.rowcount or 0),
        "users_hard_deleted": int(user_result.rowcount or 0),
        "users_leftover_blocked": int(leftover or 0),
        "run_at": now.isoformat(),
    }


__all__ = [
    "AUDIT_LOG_RETENTION_DAYS",
    "USER_DELETION_GRACE_DAYS",
    "audit_log_cutoff",
    "run_retention_cleanup",
    "user_hard_delete_cutoff",
]
