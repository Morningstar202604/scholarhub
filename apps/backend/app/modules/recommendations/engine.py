"""Content-based recommendation engine.

Builds a user interest profile from reading history (tags + disciplines
+ subdisciplines of read resources) and scores unread catalog resources
by tag overlap + discipline / subdiscipline matches. Falls back to the
latest catalog resources when the user has no reading history yet.

Scoring weights sum to 1.0 so the score stays in [0, 1]:

- tag overlap:    0.6  (precision: overlap / candidate tag count)
- discipline:     0.3  (1.0 if the candidate's discipline is in the profile)
- subdiscipline:  0.1  (1.0 if the candidate's subdiscipline is in the profile)

Cross-module reads: imports ``Resource`` (catalog) and ``ReadingHistory``
(reader) models only — no routes or schemas — per the module boundary
rules in ARCHITECTURE.md. All queries are scoped by ``tenant_id`` so
recommendations never leak across tenants (defense-in-depth with RLS).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Resource
from app.modules.reader.models import ReadingHistory

TAG_WEIGHT = 0.6
DISCIPLINE_WEIGHT = 0.3
SUBDISCIPLINE_WEIGHT = 0.1

# Cap the number of historical rows fed into the interest profile. A very
# active user with thousands of reading-history entries would otherwise
# dominate both the profile query and the per-candidate scoring loop.
# 200 recent entries is more than enough to stabilise the Counter-based
# profile; the most recent 200 read resources represent current interest.
_PROFILE_HISTORY_CAP = 200

# Cap the candidate pool scanned for scoring. Without this the engine
# loads the entire unread catalog in memory regardless of ``limit``,
# which degrades linearly with catalog size. A pool of 5× the requested
# limit (min 100) keeps result quality close to full-ranking while
# bounding memory and query cost.
_CANDIDATE_MULTIPLIER = 5
_CANDIDATE_MIN_POOL = 100

# How many of the user's top-interest tags are used as Meilisearch
# recall query terms. Using every tag would produce an overly broad OR
# that degenerates to "anything in the tenant"; the top few carry most
# of the signal.
_RECALL_QUERY_TAGS = 5


@dataclass
class UserProfile:
    """Aggregated interests extracted from the user's read resources."""

    tags: Counter[str] = field(default_factory=Counter)
    disciplines: Counter[str] = field(default_factory=Counter)
    subdisciplines: Counter[str] = field(default_factory=Counter)


@dataclass
class ScoredResource:
    """A candidate resource paired with its computed score and reason."""

    resource: Resource
    score: float
    reason: str


async def _load_read_resources(db: AsyncSession, user_id: int, tenant_id: UUID) -> list[Resource]:
    """Return the resources the user has reading history for (tenant-scoped).

    Only the most recent ``_PROFILE_HISTORY_CAP`` history entries are used
    to build the interest profile, so a user with a long reading history
    does not cause an unbounded query or an oversized profile.
    """
    rows = (
        (
            await db.execute(
                select(Resource)
                .join(ReadingHistory, ReadingHistory.resource_id == Resource.id)
                .where(
                    ReadingHistory.user_id == user_id,
                    ReadingHistory.tenant_id == tenant_id,
                )
                .order_by(desc(ReadingHistory.viewed_at), ReadingHistory.id.desc())
                .limit(_PROFILE_HISTORY_CAP)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _build_profile(read_resources: list[Resource]) -> UserProfile:
    profile = UserProfile()
    for r in read_resources:
        for tag in r.tags or []:
            profile.tags[tag] += 1
        if r.discipline:
            profile.disciplines[r.discipline] += 1
        if r.subdiscipline:
            profile.subdisciplines[r.subdiscipline] += 1
    return profile


def _score_candidate(candidate: Resource, profile: UserProfile) -> ScoredResource:
    candidate_tags = candidate.tags or []
    overlap = [t for t in candidate_tags if t in profile.tags]
    # Precision: fraction of the candidate's tags the user cares about.
    # max(..., 1) avoids division by zero for tagless candidates.
    tag_part = (len(overlap) / max(len(candidate_tags), 1)) * TAG_WEIGHT

    discipline_match = 1.0 if candidate.discipline in profile.disciplines else 0.0
    subdiscipline_match = (
        1.0
        if candidate.subdiscipline and candidate.subdiscipline in profile.subdisciplines
        else 0.0
    )
    score = (
        tag_part + discipline_match * DISCIPLINE_WEIGHT + subdiscipline_match * SUBDISCIPLINE_WEIGHT
    )
    score = max(0.0, min(1.0, score))

    parts: list[str] = []
    if overlap:
        parts.append(f"matches {len(overlap)} tags: {overlap}")
    if discipline_match:
        parts.append(f"discipline '{candidate.discipline}'")
    if subdiscipline_match:
        parts.append(f"subdiscipline '{candidate.subdiscipline}'")
    reason = "; ".join(parts) if parts else "no direct match"
    return ScoredResource(resource=candidate, score=score, reason=reason)


async def _fallback_latest(db: AsyncSession, limit: int, tenant_id: UUID) -> list[ScoredResource]:
    """Return the most recently created resources when there is no history."""
    rows = (
        (
            await db.execute(
                select(Resource)
                .where(Resource.tenant_id == tenant_id)
                .order_by(desc(Resource.created_at), Resource.id.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        ScoredResource(
            resource=r,
            score=0.0,
            reason="no reading history; showing latest",
        )
        for r in rows
    ]


async def _recall_via_search(
    profile: UserProfile, read_ids: set[int], tenant_id: UUID, pool_size: int
) -> list[int] | None:
    """Return candidate resource ids from Meilisearch keyword recall.

    Uses the user's most frequent interest tags (capped at
    ``_RECALL_QUERY_TAGS``) as a whitespace-joined query. The Meilisearch
    server ranks results by relevance, which surfaces content the user
    actually engaged with over the most-recent heuristic.

    Returns None when search is disabled, unavailable, or returns no
    results — the caller falls back to the most-recent candidate pool.
    This keeps the engine functional in offline/self-hosted deployments
    where Meilisearch is not installed or reachable (fail-open).
    """
    from app.core import search as fulltext

    if not fulltext.search_enabled():
        return None
    top_tags = [t for t, _ in profile.tags.most_common(_RECALL_QUERY_TAGS)]
    # Include the user's top discipline as an extra recall term when
    # they have a clear disciplinary focus (top discipline count ≥ 2,
    # i.e. not a one-off accidental read).
    top_disc = [d for d, _ in profile.disciplines.most_common(1)]
    if top_disc and profile.disciplines[top_disc[0]] >= 2:
        top_tags = [*top_tags, top_disc[0]]
    if not top_tags:
        return None
    q = " ".join(top_tags)
    result = await fulltext.search_resource_ids(
        tenant_id=str(tenant_id),
        q=q,
        page=1,
        page_size=pool_size,
    )
    if result is None:
        return None
    ids, _total = result
    # Exclude already-read resources.
    fresh = [i for i in ids if i not in read_ids]
    return fresh or None


async def _candidates_for_scoring(
    db: AsyncSession,
    read_ids: set[int],
    tenant_id: UUID,
    pool_size: int,
    profile: UserProfile | None = None,
) -> list[Resource]:
    """Build the candidate pool: Meilisearch recall first, fall back to
    most-recent unread resources when search is unavailable.

    The pool is always bounded to ``pool_size`` so the Python scoring
    loop never grows with catalog size.
    """
    if profile is not None:
        recalled_ids = await _recall_via_search(profile, read_ids, tenant_id, pool_size)
        if recalled_ids:
            rows = (
                (
                    await db.execute(
                        select(Resource)
                        .where(Resource.id.in_(recalled_ids), Resource.tenant_id == tenant_id)
                        .order_by(desc(Resource.created_at), Resource.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)
    # Fallback / primary path when search is off or recall returned nothing.
    rows = (
        (
            await db.execute(
                select(Resource)
                .where(~Resource.id.in_(read_ids), Resource.tenant_id == tenant_id)
                .order_by(desc(Resource.created_at), Resource.id.asc())
                .limit(pool_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def recommend(
    db: AsyncSession, user_id: int, tenant_id: UUID, limit: int
) -> list[ScoredResource]:
    """Compute top-N recommendations for the user.

    No reading history → latest ``limit`` catalog resources (score 0).
    Otherwise → unread resources ranked by content-based score, truncated
    to ``limit``. Candidate recall prefers Meilisearch keyword ranking
    when configured (surfacing content the user engaged with); when
    search is unavailable it degrades to a bounded most-recent pool.
    Ties break by resource id for deterministic ordering.

    All queries are scoped by ``tenant_id`` so recommendations never
    leak across tenants even when RLS is not active (e.g. SQLite tests).
    """
    read_resources = await _load_read_resources(db, user_id, tenant_id)
    if not read_resources:
        return await _fallback_latest(db, limit, tenant_id)

    profile = _build_profile(read_resources)
    read_ids = {r.id for r in read_resources}
    # Bound the candidate pool so the scoring loop does not grow with
    # catalog size. Take the 5× requested limit (min 100).
    candidate_pool = max(_CANDIDATE_MIN_POOL, limit * _CANDIDATE_MULTIPLIER)
    candidates = await _candidates_for_scoring(db, read_ids, tenant_id, candidate_pool, profile)

    scored = [_score_candidate(c, profile) for c in candidates]
    scored.sort(key=lambda s: (-s.score, s.resource.id))
    return scored[:limit]
