"""Review module: review_assignments + review_reports tables

Revision ID: 011_review_module
Revises: 010_user_refresh_token_version
Create Date: 2026-07-15 10:00:00

Creates the peer-review module's two tables:

- ``review_assignments`` — editor→reviewer invite with status lifecycle
  (pending → accepted/declined → completed/cancelled).
- ``review_reports`` — actual review report (1:1 with assignment).

Also adds new columns on ``submissions`` for the extended workflow:
keywords, jel_codes, corresponding_author_email, editor_note, file_path.
Widens ``submissions.status`` to 32 chars to accommodate
under_review/major_revision/minor_revision/resubmitted/accepted.

Tenant-scoped with RLS mirroring the submission strategy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "011_review_module"
down_revision: str | None = "010_user_refresh_token_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REVIEW_TABLES = ["review_assignments", "review_reports"]


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
        FOR ALL
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
        """
    )


def upgrade() -> None:
    # --- submissions: add new columns + widen status ---
    op.add_column(
        "submissions",
        sa.Column("keywords", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "submissions",
        sa.Column("jel_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.add_column(
        "submissions",
        sa.Column("corresponding_author_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("editor_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("file_path", sa.String(length=500), nullable=True),
    )
    # SQLite ALTER 改类型在 PostgreSQL 上 OK；server_default 已有，无需调整
    op.alter_column(
        "submissions", "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=32),
        existing_nullable=False,
        existing_server_default="pending",
    )

    # --- review_assignments ---
    op.create_table(
        "review_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "invited_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id", "reviewer_id", name="uq_review_assignment_submission_reviewer"
        ),
    )
    op.create_index("ix_review_assignments_tenant_id", "review_assignments", ["tenant_id"])
    op.create_index("ix_review_assignments_submission_id", "review_assignments", ["submission_id"])
    op.create_index("ix_review_assignments_reviewer_id", "review_assignments", ["reviewer_id"])
    op.create_index("ix_review_assignments_assigned_by", "review_assignments", ["assigned_by"])
    op.create_index("ix_review_assignments_status", "review_assignments", ["status"])

    # --- review_reports ---
    op.create_table(
        "review_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("recommendation", sa.String(length=32), nullable=False),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("comments_to_editor", sa.Text(), nullable=True),
        sa.Column("comments_to_author", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignment_id"], ["review_assignments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", name="uq_review_report_assignment"),
    )
    op.create_index("ix_review_reports_tenant_id", "review_reports", ["tenant_id"])
    op.create_index("ix_review_reports_assignment_id", "review_reports", ["assignment_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _REVIEW_TABLES:
            _enable_rls(table)

    # --- 角色种子：reviewer + editor ---
    # 用 INSERT ... ON CONFLICT DO NOTHING 保证幂等
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            INSERT INTO roles (tenant_id, name, description, created_at)
            SELECT t.id, 'reviewer', 'Peer reviewer (can accept/decline invitations + submit reports)', now()
            FROM tenants t
            WHERE NOT EXISTS (
                SELECT 1 FROM roles r WHERE r.tenant_id = t.id AND r.name = 'reviewer'
            );
            """
        )
        op.execute(
            """
            INSERT INTO roles (tenant_id, name, description, created_at)
            SELECT t.id, 'editor', 'Editor (assign reviewers + final decision)', now()
            FROM tenants t
            WHERE NOT EXISTS (
                SELECT 1 FROM roles r WHERE r.tenant_id = t.id AND r.name = 'editor'
            );
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _REVIEW_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_review_reports_assignment_id", table_name="review_reports")
    op.drop_index("ix_review_reports_tenant_id", table_name="review_reports")
    op.drop_table("review_reports")

    op.drop_index("ix_review_assignments_status", table_name="review_assignments")
    op.drop_index("ix_review_assignments_assigned_by", table_name="review_assignments")
    op.drop_index("ix_review_assignments_reviewer_id", table_name="review_assignments")
    op.drop_index("ix_review_assignments_submission_id", table_name="review_assignments")
    op.drop_index("ix_review_assignments_tenant_id", table_name="review_assignments")
    op.drop_table("review_assignments")

    op.alter_column(
        "submissions", "status",
        existing_type=sa.String(length=32),
        type_=sa.String(length=20),
        existing_nullable=False,
        existing_server_default="pending",
    )
    op.drop_column("submissions", "file_path")
    op.drop_column("submissions", "editor_note")
    op.drop_column("submissions", "corresponding_author_email")
    op.drop_column("submissions", "jel_codes")
    op.drop_column("submissions", "keywords")
