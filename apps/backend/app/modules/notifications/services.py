"""Internal service helpers for the notifications module.

Other modules call ``notifications.services.create()`` to insert a
notification in the same transaction as their own write — e.g. a
submission approval can fire a notification without committing twice
or coordinating HTTP round-trips.

This is intentionally a thin module-level function, not a class: there
is no state to hold, and the only call site is other modules' route
handlers that already hold an ``AsyncSession``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification

if TYPE_CHECKING:
    from uuid import UUID


async def create(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: int,
    type_: str,
    title: str,
    body: str | None = None,
    related_type: str | None = None,
    related_id: str | None = None,
) -> Notification:
    """Insert a notification row and flush so the caller's transaction owns it.

    The caller is responsible for ``commit()`` — this helper only adds
    and flushes, so the notification rides on the caller's transaction
    (rollback cancels both the business write and the notification).
    """
    notification = Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        type=type_,
        title=title,
        body=body,
        related_type=related_type,
        related_id=related_id,
    )
    db.add(notification)
    await db.flush()
    return notification


__all__ = ["create"]
