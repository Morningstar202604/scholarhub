"""Pydantic schemas for the peer-review module.

- ``AssignmentCreate``: editor→reviewer invite body.
- ``AssignmentResponse``: list/detail response.
- ``ReviewSubmit``: reviewer submits a report.
- ``ReviewReportResponse``: report payload.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import MessageResponse, PaginationMeta

AssignmentStatus = Literal["pending", "accepted", "declined", "completed", "cancelled"]
Recommendation = Literal["accept", "minor_revision", "major_revision", "reject"]


class AssignmentCreate(BaseModel):
    """Body for POST /submissions/{id}/assignments — editor invites reviewer."""

    reviewer_id: int = Field(ge=1)
    due_date: datetime | None = None


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    submission_id: int
    reviewer_id: int
    assigned_by: int | None = None
    status: AssignmentStatus
    due_date: datetime | None = None
    invited_at: datetime
    responded_at: datetime | None = None
    completed_at: datetime | None = None
    # 列表展开审稿人用户名（避免 N+1 前端要再查 user）
    reviewer_username: str | None = None
    submission_title: str | None = None


class AssignmentListResponse(BaseModel):
    data: list[AssignmentResponse]
    meta: PaginationMeta


class ReviewSubmit(BaseModel):
    """Body for POST /review/assignments/{id}/submit — reviewer submits report."""

    recommendation: Recommendation
    # scores 是自由结构 JSON：e.g. {"originality": 4, "methodology": 5, ...}
    # 不强制 schema 让不同期刊可以自定义评分维度
    scores: dict[str, Any] = Field(default_factory=dict)
    comments_to_editor: str | None = Field(default=None, max_length=20000)
    comments_to_author: str | None = Field(default=None, max_length=20000)


class ReviewReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assignment_id: int
    recommendation: Recommendation
    scores: dict[str, Any]
    comments_to_editor: str | None = None
    # 单盲模式：作者只看作者评论 + 推荐，看不到审稿人身份 + editor-only 评论
    comments_to_author: str | None = None
    submitted_at: datetime


__all__ = [
    "AssignmentCreate",
    "AssignmentListResponse",
    "AssignmentResponse",
    "AssignmentStatus",
    "MessageResponse",
    "PaginationMeta",
    "Recommendation",
    "ReviewReportResponse",
    "ReviewSubmit",
]
