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
    """Return the resources the user has reading history for (tenant-scoped)."""
    rows = (
        (
            await db.execute(
                select(Resource)
                .join(ReadingHistory, ReadingHistory.resource_id == Resource.id)
                .where(
                    ReadingHistory.user_id == user_id,
                    ReadingHistory.tenant_id == tenant_id,
                )
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


async def recommend(
    db: AsyncSession, user_id: int, tenant_id: UUID, limit: int
) -> list[ScoredResource]:
    """Compute top-N recommendations for the user.

    No reading history → latest ``limit`` catalog resources (score 0).
    Otherwise → unread resources ranked by content-based score, truncated
    to ``limit``. Ties break by resource id for deterministic ordering.

    All queries are scoped by ``tenant_id`` so recommendations never
    leak across tenants even when RLS is not active (e.g. SQLite tests).
    """
    read_resources = await _load_read_resources(db, user_id, tenant_id)
    if not read_resources:
        return await _fallback_latest(db, limit, tenant_id)

    profile = _build_profile(read_resources)
    read_ids = {r.id for r in read_resources}
    candidates = (
        (
            await db.execute(
                select(Resource).where(
                    ~Resource.id.in_(read_ids),
                    Resource.tenant_id == tenant_id,
                )
            )
        )
        .scalars()
        .all()
    )

    scored = [_score_candidate(c, profile) for c in candidates]
    scored.sort(key=lambda s: (-s.score, s.resource.id))
    return scored[:limit]
