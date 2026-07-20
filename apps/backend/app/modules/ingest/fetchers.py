"""Metadata fetchers — Crossref (DOI) and arXiv (arXiv ID) → IngestResource.

Both fetchers are stateless async functions. They raise:

- ``ResourceNotFoundError`` when the upstream reports the id is unknown
  (maps to 404 in the route layer).
- ``UpstreamError`` when the upstream times out, returns a 5xx, or any
  other transport error occurs (maps to 502).

Each fetcher builds a fresh ``httpx.AsyncClient`` with a 10s timeout.
Tests monkeypatch these functions (or the underlying ``httpx`` call) so
no real network request is ever made in the suite.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.modules.ingest.schemas import IngestResource

# Crossref politely asks callers to identify themselves with a mailto.
# Read from settings; falls back to a placeholder if not configured.
CROSSREF_MAILTO = settings.crossref_mailto or "scholarhub-operator@example.com"
CROSSREF_BASE_URL = "https://api.crossref.org/works"
# Use HTTPS for arXiv (same host/path as the plaintext endpoint) to prevent
# in-transit tampering by a man-in-the-middle.
ARXIV_BASE_URL = "https://export.arxiv.org/api/query"
HTTP_TIMEOUT = 10.0

# Atom namespace used by the arXiv API response.
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class ResourceNotFoundError(Exception):
    """Upstream reports the DOI/arXiv ID does not exist."""


class UpstreamError(Exception):
    """Upstream timed out or returned an error status."""


def _crossref_authors(message: Mapping[str, Any]) -> list[str]:
    """Crossref authors are ``{given, family}`` dicts → ``"given family"``."""
    out: list[str] = []
    for author in message.get("author") or []:
        given = (author.get("given") or "").strip()
        family = (author.get("family") or "").strip()
        if given and family:
            out.append(f"{given} {family}")
        elif family:
            out.append(family)
        elif given:
            out.append(given)
    return out


def _crossref_year(message: Mapping[str, Any]) -> int | None:
    """Crossref dates nest under ``date-parts`` as a list of lists."""
    for key in ("published-print", "published-online", "issued", "created"):
        block = message.get(key)
        if not block:
            continue
        parts = block.get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


async def fetch_crossref(doi: str) -> IngestResource:
    """Fetch a single work by DOI from the Crossref REST API."""
    # URL-encode the DOI so a '?' inside it cannot inject extra query params.
    url = f"{CROSSREF_BASE_URL}/{quote(doi, safe='/')}"
    headers = {
        "User-Agent": f"ScholarHUB/0.1 (mailto:{CROSSREF_MAILTO})",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException as exc:
        raise UpstreamError(f"Crossref timeout: {exc}") from exc
    except httpx.RequestError as exc:
        raise UpstreamError(f"Crossref request failed: {exc}") from exc

    if response.status_code == 404:
        raise ResourceNotFoundError(f"DOI not found: {doi}")
    if response.status_code >= 400:
        raise UpstreamError(f"Crossref returned status {response.status_code} for {doi}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamError(f"Crossref returned non-JSON body: {exc}") from exc

    message = payload.get("message")
    if not message:
        raise UpstreamError("Crossref response missing 'message' field")

    title_list = message.get("title") or []
    title = title_list[0].strip() if title_list else ""
    if not title:
        raise ResourceNotFoundError(f"Crossref record for {doi} has no title")

    authors = _crossref_authors(message)
    if not authors:
        raise ResourceNotFoundError(f"Crossref record for {doi} has no authors")

    container = message.get("container-title") or []
    venue = container[0].strip() if container else None

    return IngestResource(
        title=title,
        type="paper",
        authors=authors,
        year=_crossref_year(message),
        venue=venue,
        discipline="unknown",
        tags=[],
        abstract=(message.get("abstract") or "").strip(),
        doi=doi,
    )


def _arxiv_text(entry: ET.Element, tag: str) -> str:
    """Read a namespaced Atom child's text, or empty string if absent."""
    node = entry.find(f"{_ATOM_NS}{tag}")
    return (node.text or "").strip() if node is not None and node.text else ""


def _arxiv_authors(entry: ET.Element) -> list[str]:
    out: list[str] = []
    for author_node in entry.findall(f"{_ATOM_NS}author"):
        name_node = author_node.find(f"{_ATOM_NS}name")
        if name_node is not None and name_node.text:
            name = name_node.text.strip()
            if name:
                out.append(name)
    return out


async def fetch_arxiv(arxiv_id: str) -> IngestResource:
    """Fetch a single paper by arXiv ID from the arXiv Atom API."""
    # URL-encode the arXiv id so an '&' inside it cannot inject extra query params.
    url = f"{ARXIV_BASE_URL}?id_list={quote(arxiv_id, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise UpstreamError(f"arXiv timeout: {exc}") from exc
    except httpx.RequestError as exc:
        raise UpstreamError(f"arXiv request failed: {exc}") from exc

    if response.status_code == 404:
        raise ResourceNotFoundError(f"arXiv ID not found: {arxiv_id}")
    if response.status_code >= 400:
        raise UpstreamError(f"arXiv returned status {response.status_code} for {arxiv_id}")

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        raise UpstreamError(f"arXiv returned invalid XML: {exc}") from exc

    # Atom feed entries live directly under the root <feed> element.
    entries = [child for child in root if child.tag == f"{_ATOM_NS}entry"]
    if not entries:
        # arXiv returns an empty feed when the id is unknown.
        raise ResourceNotFoundError(f"arXiv ID not found: {arxiv_id}")

    entry = entries[0]
    title = _arxiv_text(entry, "title")
    if not title:
        raise ResourceNotFoundError(f"arXiv record for {arxiv_id} has no title")

    authors = _arxiv_authors(entry)
    if not authors:
        raise ResourceNotFoundError(f"arXiv record for {arxiv_id} has no authors")

    year = None
    published = _arxiv_text(entry, "published")
    if published:
        # arXiv timestamps look like "2024-01-15T00:00:00Z".
        year = _safe_parse_year(published[:4])

    venue_node = entry.find(f"{_ARXIV_NS}journal_ref")
    venue = venue_node.text.strip() if venue_node is not None and venue_node.text else None

    doi_node = entry.find(f"{_ARXIV_NS}doi")
    doi = doi_node.text.strip() if doi_node is not None and doi_node.text else None

    abstract = _arxiv_text(entry, "summary")

    return IngestResource(
        title=title,
        type="preprint",
        authors=authors,
        year=year,
        venue=venue,
        discipline="unknown",
        tags=[],
        abstract=abstract,
        doi=doi,
    )


def _safe_parse_year(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


__all__ = [
    "ARXIV_BASE_URL",
    "CROSSREF_BASE_URL",
    "CROSSREF_MAILTO",
    "HTTP_TIMEOUT",
    "ResourceNotFoundError",
    "UpstreamError",
    "fetch_arxiv",
    "fetch_crossref",
]
