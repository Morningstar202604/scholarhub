"""SQLAlchemy model for DOI registration tracking.

``doi_registrations`` keeps a record of every DOI minted or updated
through the DataCite API. The table is append-only: each row captures
one registration event so the history is auditable.

The actual DOI metadata is stored on the ``resources`` table (the
``doi`` column) and in the DataCite index. This table is purely a
local audit trail + status tracker.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models import Base


class DOIRegistration(Base):
    """Audit record for a DOI mint/update event."""

    __tablename__ = "doi_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The resource this DOI was registered for.
    resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The DOI that was registered (e.g. "10.12345/abc-def-ghi").
    doi: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # Registration state: "pending" | "completed" | "failed"
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # DataCite API response / error message.
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Who triggered this registration.
    registered_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


__all__ = ["DOIRegistration"]
