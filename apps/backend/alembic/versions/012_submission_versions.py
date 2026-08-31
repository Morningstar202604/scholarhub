"""Submission versioning: submission_versions snapshot table

Revision ID: 012_submission_versions
Revises: 011_review_module
Create Date: 2026-07-30 10:00:00

Adds the ``submission_versions`` table — append-only snapshots of a
submission's bibliographic payload:

- v1 is taken when the author first creates the submission;
- v2..n are taken on each resubmit after major/minor revision, with an
  optional author note ("what changed in response to review").

Payload is stored as a whole JSONB blob (not column-by-column) so
future Submission field additions never require another migration
here. Tenant-scoped with RLS mirroring the submission strategy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "012_submission_versions"
down_revision: str | None = "011_review_module"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "submission_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "version", name="uq_submission_version_number"),
    )
    op.create_index("ix_submission_versions_tenant_id", "submission_versions", ["tenant_id"])
    op.create_index(
        "ix_submission_versions_submission_id",
        "submission_versions",
        ["submission_id"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE submission_versions ENABLE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE submission_versions FORCE ROW LEVEL SECURITY;")
        op.execute(
            """
            CREATE POLICY tenant_isolation ON submission_versions
            FOR ALL
            USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
            """
        )

        # 历史数据回填：把每条既有 submission 的当前 payload 存为 v1，
        # 让「版本历史」端点对老数据也能返回至少一个版本。
        op.execute(
            """
            INSERT INTO submission_versions
                (tenant_id, submission_id, version, payload, file_path,
                 note, created_by, created_at)
            SELECT
                s.tenant_id, s.id, 1,
                jsonb_build_object(
                    'title', s.title,
                    'type', s.type,
                    'authors', s.authors,
                    'year', s.year,
                    'venue', s.venue,
                    'discipline', s.discipline,
                    'subdiscipline', s.subdiscipline,
                    'keywords', s.keywords,
                    'jel_codes', s.jel_codes,
                    'tags', s.tags,
                    'abstract', s.abstract,
                    'preview', s.preview,
                    'download_url', s.download_url,
                    'external_url', s.external_url,
                    'doi', s.doi,
                    'corresponding_author_email', s.corresponding_author_email
                ),
                s.file_path, NULL, s.submitted_by, s.submitted_at
            FROM submissions s
            WHERE NOT EXISTS (
                SELECT 1 FROM submission_versions v
                WHERE v.submission_id = s.id
            );
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON submission_versions;")
        op.execute("ALTER TABLE submission_versions NO FORCE ROW LEVEL SECURITY;")
        op.execute("ALTER TABLE submission_versions DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_submission_versions_submission_id", table_name="submission_versions")
    op.drop_index("ix_submission_versions_tenant_id", table_name="submission_versions")
    op.drop_table("submission_versions")
