"""Performance indexes for tenant-scoped list endpoints

Revision ID: 020_performance_indexes
Revises: 019_two_factor_converge_m5_to_m2
Create Date: 2026-09-12 00:00:00

Adds covering / composite indexes that match the actual access patterns
of the high-traffic list endpoints:

- reading_history: (tenant_id, user_id, viewed_at DESC, id) for the
  "my recent reads" list.
- submissions: (tenant_id, status, submitted_at DESC, id) for the
  editor dashboard and (tenant_id, submitted_at DESC, id) for the
  "all my submissions" list.
- review_assignments: (tenant_id, reviewer_id, status, invited_at DESC, id)
  for the reviewer inbox.
- audit_logs.actor_user_id: FK column without an index.
- submission_versions.created_by: FK column without an index.

SQLite (test env): all statements are no-ops, so the test suite runs
against the un-indexed tables without issue.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020_performance_indexes"
down_revision: str | Sequence[str] | None = "019_two_factor_converge_m5_to_m2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reading_history_composite "
        "ON reading_history (tenant_id, user_id, viewed_at DESC, id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_submissions_editor_list "
        "ON submissions (tenant_id, status, submitted_at DESC, id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_submissions_recent "
        "ON submissions (tenant_id, submitted_at DESC, id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_review_assignments_inbox "
        "ON review_assignments "
        "(tenant_id, reviewer_id, status, invited_at DESC, id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_user_id "
        "ON audit_logs (actor_user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_submission_versions_created_by "
        "ON submission_versions (created_by)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_submission_versions_created_by")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_actor_user_id")
    op.execute("DROP INDEX IF EXISTS ix_review_assignments_inbox")
    op.execute("DROP INDEX IF EXISTS ix_submissions_recent")
    op.execute("DROP INDEX IF EXISTS ix_submissions_editor_list")
    op.execute("DROP INDEX IF EXISTS ix_reading_history_composite")
