"""add publisher and short_container_title to resources

Revision ID: 016_publisher
Create Date: 2025-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "016_publisher"
down_revision: str | None = "015_discipline_ontology"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("publisher", sa.String(500), nullable=True))
    op.add_column("resources", sa.Column("short_container_title", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("resources", "short_container_title")
    op.drop_column("resources", "publisher")
