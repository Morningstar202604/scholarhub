"""Pydantic schemas for the DOI module."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DOIRegisterRequest(BaseModel):
    """Body for POST /api/doi/register."""

    resource_id: int = Field(ge=1, description="ID of the catalog resource to mint a DOI for")
    # Optional: override the auto-generated DOI suffix. If omitted, the
    # server generates one (e.g. from the resource slug or id).
    doi_suffix: str | None = Field(default=None, max_length=100)


class DOIRegistrationResponse(BaseModel):
    """Response for a DOI registration request."""

    id: int
    resource_id: int
    doi: str
    state: str
    message: str | None
    created_at: datetime


class DOIStatusResponse(BaseModel):
    """Status of a DOI — returned by GET /api/doi/{resource_id}/status."""

    doi: str | None
    state: Literal["none", "pending", "completed", "failed"]
    registered_at: datetime | None
    message: str | None


__all__ = [
    "DOIRegisterRequest",
    "DOIRegistrationResponse",
    "DOIStatusResponse",
]