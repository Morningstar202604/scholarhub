"""merge webauthn and publisher-two-factor heads

Revision ID: 85ef346eae63
Revises: 018_user_webauthn, 51688fb04bf7
Create Date: 2026-09-11 13:12:31.155203
"""

from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '85ef346eae63'
down_revision: str | None = ('018_user_webauthn', '51688fb04bf7')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
