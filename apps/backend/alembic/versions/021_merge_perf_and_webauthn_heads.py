"""Merge 020_performance_indexes with 85ef346eae63 (webauthn+publisher-two-factor heads)

Revision ID: 021_merge_perf_and_webauthn_heads
Revises: 020_performance_indexes, 85ef346eae63
Create Date: 2026-09-12 00:01:00

Both branches were created independently; this empty merge node unifies
them so ``alembic upgrade head`` has a single head again.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "021_merge_perf_and_webauthn_heads"
down_revision: str | Sequence[str] | None = ("020_performance_indexes", "85ef346eae63")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
