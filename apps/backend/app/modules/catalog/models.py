"""SQLAlchemy models for the catalog module.

Two tables, both tenant-scoped with RLS:

- ``resources`` — core bibliographic record (title, authors, year, venue,
  discipline, tags, abstract, DOI, journal metadata). No citation cache
  and no view/download counters here (those live in ``resource_stats``).
- ``resource_stats`` — write-heavy counters (views, downloads, citation
  count) split out to avoid contention on the catalog row.

The optional ``Author`` table for ORCID/affiliation enrichment is
reserved for a future phase; the primary author storage is the JSON
``authors`` column on ``resources``.

All catalog models inherit from the core ``Base`` so cross-module FKs
(e.g. ``resources.tenant_id → tenants.id``) resolve without metadata
gymnastics. This matches ARCHITECTURE.md "All modules share the
tenant's PostgreSQL database".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models import Base, JSONBVariant


class Resource(Base):
    """A catalog record (paper / book / dataset / tutorial / ...).

    The ``slug`` is an optional stable URL identifier. When absent, the
    frontend uses the integer id. ``authors`` is the primary author
    storage (JSON list[str]); structured author entities with ORCID etc.
    are a future concern (reserved ``Author`` table).
    """

    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_resources_tenant_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional stable URL slug. Unique per tenant; null allowed for records
    # imported without a slug (frontend falls back to int id).
    slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Primary author storage. JSON list[str], e.g. ["Alice Author", "Bob"].
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    discipline: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subdiscipline: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    preview: Mapped[str] = mapped_column(Text, nullable=False)
    download_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    # Journal metadata (Phase 1)
    volume: Mapped[str | None] = mapped_column(String(50), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pages: Mapped[str | None] = mapped_column(String(50), nullable=True)
    issn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    isbn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    publication_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="published"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    stats: Mapped[list[ResourceStat]] = relationship(
        back_populates="resource", cascade="all, delete-orphan", uselist=True
    )


class ResourceStat(Base):
    """Per-resource counters, split out to avoid write hotspots on the
    catalog row. Updated by read/download endpoints; read by list/detail.

    One row per resource (created lazily on first stat event). NULL
    counters mean "no data yet", not "zero".
    """

    __tablename__ = "resource_stats"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_id", name="uq_resource_stats_tenant_resource"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # External citation count (e.g. from Semantic Scholar). NULL = not yet fetched.
    citations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONBVariant, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    resource: Mapped[Resource] = relationship(back_populates="stats")


__all__ = ["Resource", "ResourceStat"]

