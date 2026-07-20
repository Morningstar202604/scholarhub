"""SQLAlchemy model for the submission module.

Single table, tenant-scoped with RLS:

- ``submissions`` — author-submitted bibliographic record awaiting
  editor review. Mirrors the catalog ``Resource`` field shape so an
  approval can materialize a Resource with no field reshuffling. The
  ``resource_id`` column is set when (and only when) the submission is
  approved and the corresponding catalog Resource has been created.

The reviewer + submitter FKs point at ``users.id`` in the core schema;
the resource FK points at ``catalog.resources.id``. All cross-module FKs
resolve naturally because the submission model inherits from the core
``Base`` (ARCHITECTURE.md "All modules share the tenant's PostgreSQL
database").
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models import Base, JSONBVariant, User

if TYPE_CHECKING:
    # Resource lives in the catalog module; import lazily under
    # TYPE_CHECKING to avoid a circular import at module load time
    # (submission depends on catalog; importing catalog here would
    # re-trigger its own __init__ registration).
    from app.modules.catalog.models import Resource


class Submission(Base):
    """An author-submitted record awaiting editor review.

    Status lifecycle: ``pending`` → ``approved`` | ``rejected``
    (terminal). Once approved, ``resource_id`` points at the
    catalog Resource materialized from this submission; until then it
    is NULL.
    """

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Author / submitter. CASCADE so deleting a user removes their
    # submissions (consistent with how catalog handles ownership).
    submitted_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Reviewer. SET NULL so historical approvals survive a reviewer
    # account being deleted (the approved resource must outlive the
    # reviewer's account).
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Catalog Resource created on approval. SET NULL so deleting a
    # catalog Resource does not silently rewrite submission history
    # (the submission record itself is the source of truth for "this
    # author submitted this on this date").
    resource_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("resources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Bibliographic payload — mirrors catalog ResourceBase so approval
    # can materialize a Resource with no field reshuffling.
    title: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSONBVariant, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    discipline: Mapped[str] = mapped_column(String(100), nullable=False)
    subdiscipline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 关键词 + JEL 分类码：补 submission → catalog 物化时丢失的字段
    keywords: Mapped[list[str]] = mapped_column(JSONBVariant, nullable=False, default=list)
    jel_codes: Mapped[list[str]] = mapped_column(JSONBVariant, nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONBVariant, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    preview: Mapped[str] = mapped_column(Text, nullable=False)
    download_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    corresponding_author_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Workflow fields。
    # status 兼容旧值 pending/approved/rejected，同时支持
    # under_review/major_revision/minor_revision/resubmitted/accepted。
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 编辑 4 元决定（accept/minor_revision/major_revision/reject）的备注，
    # 区别于 admin_note（兼容旧 review 端点的备注字段）
    editor_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    submitter: Mapped[User] = relationship(
        "User", foreign_keys="Submission.submitted_by"
    )
    reviewer: Mapped[User | None] = relationship(
        "User", foreign_keys="Submission.reviewed_by"
    )
    # Resource lives in the catalog module; import lazily (string ref)
    # to avoid a circular import at module load time.
    resource: Mapped[Resource | None] = relationship("Resource")


__all__ = ["Submission"]
