"""Pydantic schemas for the catalog module.

Public read endpoints use ``ResourceResponse``; admin write endpoints
use ``ResourceCreate`` / ``ResourceUpdate``. List responses carry
pagination metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.schemas import Authors, PaginationMeta


class AuthorMeta(BaseModel):
    """Per-author enrichment object.

    Parallel to the ``authors`` list (which is the display source of
    truth). ``name`` matches the corresponding entry in ``authors``
    by position; ``orcid`` and ``affiliation`` / ``email`` are
    optional metadata.

    Validation: ``orcid`` is canonicalised by ``app.core.orcid``.
    """

    name: str = Field(min_length=1, max_length=200)
    orcid: str | None = Field(default=None, max_length=20)
    affiliation: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=255)

    @field_validator("orcid")
    @classmethod
    def _canonicalise_orcid(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        from app.core.orcid import is_valid_orcid, normalize_orcid

        if not is_valid_orcid(value):
            raise ValueError(f"Invalid ORCID iD: {value!r}")
        return normalize_orcid(value)


# Resource type enum; may grow per deployment.
ResourceType = Literal["paper", "book", "dataset", "tutorial"]
PublicationStatus = Literal["published", "in_review", "draft"]


class ResourceBase(BaseModel):
    """Shared fields for create / update / response."""

    type: ResourceType
    title: str = Field(min_length=1, max_length=1000)
    authors: Authors = Field(min_length=1, max_length=200)
    year: int = Field(ge=-3000, le=2100)
    venue: str | None = Field(default=None, max_length=500)
    discipline: str = Field(min_length=1, max_length=100)
    subdiscipline: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=50)
    abstract: str = Field(min_length=1, max_length=20000)
    # Optional preview; falls back to the first 500 chars of abstract (matches SubmissionCreate).
    preview: str | None = Field(default=None, max_length=5000)
    download_url: AnyHttpUrl | None = None
    external_url: AnyHttpUrl | None = None
    doi: str | None = Field(default=None, max_length=200)
    # Optional parallel list of author enrichment objects. Must have
    # the same length as ``authors`` (when set), or be empty/null.
    authors_meta: list[AuthorMeta] | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _authors_meta_length_matches(self) -> ResourceBase:
        if self.authors_meta is None:
            return self
        # Off-by-one checks: the metadata list is optional and may be
        # shorter (caller only knows ORCID for some authors) but must
        # never claim more entries than the authors list.
        if len(self.authors_meta) > len(self.authors):
            raise ValueError(
                f"authors_meta has {len(self.authors_meta)} entries but "
                f"authors has only {len(self.authors)}"
            )
        return self

    # Journal metadata
    volume: str | None = Field(default=None, max_length=50)
    issue: str | None = Field(default=None, max_length=50)
    pages: str | None = Field(default=None, max_length=50)
    issn: str | None = Field(default=None, max_length=20)
    isbn: str | None = Field(default=None, max_length=20)
    publisher: str | None = Field(default=None, max_length=500)
    short_container_title: str | None = Field(default=None, max_length=200)
    keywords: list[str] | None = Field(default=None, max_length=50)
    language: str = Field(default="en", max_length=10)
    publication_status: PublicationStatus = "published"

    @model_validator(mode="after")
    def _fill_preview_from_abstract(self) -> ResourceBase:
        if not self.preview:
            # Fall back to the first 500 chars of abstract; stays under the 5000-char limit.
            self.preview = (self.abstract or "")[:500]
        return self


class ResourceCreate(ResourceBase):
    """Body for POST /catalog/."""

    slug: str | None = Field(default=None, min_length=1, max_length=100)


class ResourceUpdate(BaseModel):
    """Body for PATCH /catalog/{id}. All fields optional."""

    type: ResourceType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    authors: list[str] | None = Field(default=None, min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=-3000, le=2100)
    venue: str | None = Field(default=None, max_length=500)
    discipline: str | None = Field(default=None, min_length=1, max_length=100)
    subdiscipline: str | None = Field(default=None, max_length=100)
    tags: list[str] | None = Field(default=None, max_length=50)
    abstract: str | None = Field(default=None, min_length=1, max_length=20000)
    preview: str | None = Field(default=None, min_length=1, max_length=5000)
    # Use AnyHttpUrl | None (matching ResourceBase) so the URL scheme is
    # constrained to http/https. A plain str | None would accept
    # javascript: and other dangerous schemes, enabling stored XSS.
    download_url: AnyHttpUrl | None = None
    external_url: AnyHttpUrl | None = None
    doi: str | None = Field(default=None, max_length=200)
    volume: str | None = Field(default=None, max_length=50)
    issue: str | None = Field(default=None, max_length=50)
    pages: str | None = Field(default=None, max_length=50)
    issn: str | None = Field(default=None, max_length=20)
    isbn: str | None = Field(default=None, max_length=20)
    publisher: str | None = Field(default=None, max_length=500)
    short_container_title: str | None = Field(default=None, max_length=200)
    keywords: list[str] | None = Field(default=None, max_length=50)
    language: str | None = Field(default=None, max_length=10)
    publication_status: PublicationStatus | None = None
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    authors_meta: list[AuthorMeta] | None = Field(default=None, max_length=200)


class ResourceResponse(ResourceBase):
    """Response body for read endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _coerce_authors_meta(cls, data: Any) -> Any:
        """Map the JSON column ``authors_meta`` (list[dict]) into a
        list of :class:`AuthorMeta` for the response. When ``data``
        is a plain dict we just leave it alone (Pydantic does the
        construction). For ORM instances we extract the column by
        name and replace the list of dicts with Pydantic models.
        """
        if hasattr(data, "_sa_instance_state"):
            # ORM: take the raw value and let Pydantic build the models
            raw = getattr(data, "authors_meta", None)
            return {c.name: getattr(data, c.name) for c in data.__table__.columns} | {
                "authors_meta": raw
            }
        return data


class ResourceListResponse(BaseModel):
    data: list[ResourceResponse]
    meta: PaginationMeta


class ResourceStats(BaseModel):
    total: int
    by_type: dict[str, int]
    by_discipline: dict[str, int]


class FacetBucket(BaseModel):
    value: str
    count: int


class ResourceFacets(BaseModel):
    years: list[FacetBucket]
    tags: list[FacetBucket]


__all__ = [
    "AuthorMeta",
    "FacetBucket",
    "PaginationMeta",
    "PublicationStatus",
    "ResourceBase",
    "ResourceCreate",
    "ResourceFacets",
    "ResourceListResponse",
    "ResourceResponse",
    "ResourceStats",
    "ResourceType",
    "ResourceUpdate",
]
