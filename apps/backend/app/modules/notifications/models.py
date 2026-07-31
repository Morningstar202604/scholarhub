"""SQLAlchemy model for the notifications module.

Single table, tenant-scoped with RLS:

- ``notifications`` — one row per (tenant, user, notification). The
  ``user_id`` is the recipient; notifications are strictly per-user
  (no shared "team" stream). ``related_type`` / ``related_id`` are
  optional opaque pointers (e.g. "submission"/"123") so the recipient
  can deep-link to the source object without a hard FK.

The recipient FK points at ``users.id`` in the core schema. The model
inherits from the core ``Base`` so cross-module FKs resolve without
metadata gymnastics (ARCHITECTURE.md "All modules share the tenant's
PostgreSQL database").
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models import Base

if TYPE_CHECKING:
    from app.models import User


class Notification(Base):
    """An in-app notification addressed to one user.

    ``type`` is a short stable slug (e.g. ``submission_approved``,
    ``submission_rejected``, ``system``) the frontend uses to pick an
    icon / route. ``related_type`` / ``related_id`` are opaque
    pointers — no FK — so a notification survives the source object
    being deleted (the recipient still sees "your submission was
    approved" even after the catalog Resource is later removed).
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Recipient. CASCADE so deleting a user removes their notifications
    # (consistent with how the rest of the schema handles ownership).
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Opaque pointers — no FK. Lets the source object (e.g. a catalog
    # Resource) be deleted without invalidating the historical
    # notification record.
    related_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped[User] = relationship("User", foreign_keys="Notification.user_id")


__all__ = ["Notification"]
