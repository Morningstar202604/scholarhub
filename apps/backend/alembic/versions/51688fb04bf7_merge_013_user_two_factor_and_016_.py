"""merge 013_user_two_factor and 016_publisher

Revision ID: 51688fb04bf7
Revises: 013_user_two_factor, 016_publisher
Create Date: 2026-08-06 16:20:13.525871
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '51688fb04bf7'
down_revision: Union[str, None] = ('013_user_two_factor', '016_publisher')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
