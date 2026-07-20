"""Pydantic schemas for the ingest module.

The ingest module normalises external bibliographic data (BibTeX/RIS/CSV
files, Crossref/arXiv API responses) into ``IngestResource`` objects.
These objects are *not* catalog rows — the frontend takes them and
submits them via ``/api/submissions`` so the catalog keeps a single
write path.

``IngestResource`` deliberately mirrors the field shape of
``SubmissionCreate`` but is more permissive (year/abstract/discipline
optional) because parsed or fetched data may be incomplete; the user
fills gaps before submitting.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.schemas import Authors

# Broader than catalog's ResourceType: ingest can produce types the
# catalog does not yet accept (e.g. thesis, preprint) — the frontend
# either maps them or asks the user to pick before submitting.
IngestResourceType = Literal[
    "paper",
    "book",
    "journal",
    "preprint",
    "thesis",
    "dataset",
    "tutorial",
]

ParseFormat = Literal["bibtex", "ris", "csv"]
FetchSource = Literal["crossref", "arxiv"]


class IngestResource(BaseModel):
    """Normalised record produced by parsers and fetchers.

    Field shape mirrors ``SubmissionCreate`` so the frontend can forward
    an object verbatim to ``POST /api/submissions`` after the user fills
    any missing required fields (year, abstract, discipline).
    """

    title: str = Field(min_length=1, max_length=1000)
    type: IngestResourceType
    authors: Authors = Field(min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=-3000, le=2100)
    venue: str | None = Field(default=None, max_length=500)
    discipline: str = Field(default="unknown", max_length=100)
    subdiscipline: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=50)
    abstract: str = Field(default="", max_length=20000)
    doi: str | None = Field(default=None, max_length=200)


class ParseRequest(BaseModel):
    """Body for POST /api/ingest/parse."""

    format: ParseFormat
    content: str = Field(min_length=1, max_length=2_000_000)


class FetchRequest(BaseModel):
    """Body for POST /api/ingest/fetch."""

    source: FetchSource
    id: str = Field(min_length=1, max_length=500)


class ParseError(BaseModel):
    """Per-entry parse error — line is 1-based for CSV rows, otherwise
    the 1-based index of the offending entry in source order."""

    line: int = Field(ge=1)
    error: str = Field(min_length=1, max_length=500)


class ParseResponse(BaseModel):
    """Response for POST /api/ingest/parse."""

    data: list[IngestResource]
    count: int = Field(ge=0)
    errors: list[ParseError]


__all__ = [
    "FetchRequest",
    "FetchSource",
    "IngestResource",
    "IngestResourceType",
    "ParseError",
    "ParseFormat",
    "ParseRequest",
    "ParseResponse",
]
