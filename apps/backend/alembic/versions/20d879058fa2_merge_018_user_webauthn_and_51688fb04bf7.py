"""merge 018_user_webauthn and 51688fb04bf7

Revision ID: 20d879058fa2
Revises: 018_user_webauthn, 51688fb04bf7
Create Date: 2026-09-14 06:47:11.205585

This is a pure merge revision: it joins the two migration branches that
grew independently (per-module migrations are authored in parallel) so
that ``alembic upgrade head`` resolves to a single head again.

Without it, ``upgrade head`` fails with "Multiple head revisions are
present", which breaks every documented deploy path (README quick start
and the backend image CMD).
"""

from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "20d879058fa2"
down_revision: str | tuple[str, ...] | None = ("018_user_webauthn", "51688fb04bf7")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Both branches are already applied on existing databases; nothing to do.
    pass


def downgrade() -> None:
    # Merge point only — downgrading is handled by the individual branches.
    pass
