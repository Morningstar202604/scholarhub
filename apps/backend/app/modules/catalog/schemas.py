"""Pydantic schemas for the catalog module.

Public read endpoints use ``ResourceResponse``; admin write endpoints
use ``ResourceCreate`` / ``ResourceUpdate``. List responses carry
pagination metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from app.core.schemas import Authors, PaginationMeta

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

    # Journal metadata
    volume: str | None = Field(default=None, max_length=50)
    issue: str | None = Field(default=None, max_length=50)
    pages: str | None = Field(default=None, max_length=50)
    issn: str | None = Field(default=None, max_length=20)
    isbn: str | None = Field(default=None, max_length=20)
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
    keywords: list[str] | None = Field(default=None, max_length=50)
    language: str | None = Field(default=None, max_length=10)
    publication_status: PublicationStatus | None = None
    slug: str | None = Field(default=None, min_length=1, max_length=100)


class ResourceResponse(ResourceBase):
    """Response body for read endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str | None = None
    created_at: datetime
    updated_at: datetime


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
