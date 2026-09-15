"""补 submission 模块主干路径的单测：审稿分配、编辑决断、作者重投、单盲、稿件文件。

背景：``app/modules/submission/routes.py`` 单测覆盖仅 33%，未覆盖区间集中在
``assign_reviewer`` / ``list_assignments`` / ``cancel_assignment`` /
``list_review_reports`` / ``editor_decision`` / ``author_resubmit`` /
``upload_submission_file`` / ``download_submission_file``。E2E 覆盖了
submission→review→accept 的 happy path，但**越权、非法状态流转、单盲剥离**
这类边界条件 E2E 走不到，只能靠单测守住。
"""

from __future__ import annotations

from datetime import UTC, datetime

from conftest import auth_headers
from httpx import AsyncClient
from sqlalchemy import select

from app.modules.review.models import ReviewAssignment, ReviewReport

_PAYLOAD = {
    "title": "Workflow Coverage Specimen",
    "type": "paper",
    "authors": ["Alice Author"],
    "year": 2024,
    "venue": "Journal of Testing",
    "discipline": "physics",
    "subdiscipline": "quantum",
    "tags": ["workflow"],
    "abstract": "A submission used to exercise the review workflow endpoints.",
    "preview": "Short preview.",
}


async def _create_submission(client: AsyncClient, user: dict) -> dict:
    response = await client.post("/api/submissions", json=_PAYLOAD, headers=auth_headers(user))
    response.raise_for_status()
    return response.json()


async def _register(client: AsyncClient, username: str, email: str) -> dict:
    """注册一个额外的普通用户（审稿人 / 无关第三方）。"""
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": "password123"},
    )
    response.raise_for_status()
    data = response.json()
    return {"token": data["access_token"], "user_id": data["user_id"], "username": username}


async def _get(client: AsyncClient, submission_id: int, user: dict) -> dict:
    response = await client.get(f"/api/submissions/{submission_id}", headers=auth_headers(user))
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# A. 审稿人分配
# ---------------------------------------------------------------------------


async def test_admin_assigns_reviewer_flips_status_to_under_review(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)
    reviewer = await _register(client, "rev_one", "rev1@example.com")

    response = await client.post(
        f"/api/submissions/{sub['id']}/assignments",
        json={"reviewer_id": reviewer["user_id"]},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["reviewer_id"] == reviewer["user_id"]
    assert body["status"] == "pending"
    assert body["reviewer_username"] == "rev_one"

    # pending → under_review（仅 pending 时自动翻转）
    assert (await _get(client, sub["id"], admin_user))["status"] == "under_review"


async def test_non_editor_cannot_assign_reviewer(client: AsyncClient, test_user: dict) -> None:
    sub = await _create_submission(client, test_user)
    reviewer = await _register(client, "rev_two", "rev2@example.com")

    response = await client.post(
        f"/api/submissions/{sub['id']}/assignments",
        json={"reviewer_id": reviewer["user_id"]},
        headers=auth_headers(test_user),
    )
    assert response.status_code == 403


async def test_assign_reviewer_rejects_unknown_reviewer(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)

    response = await client.post(
        f"/api/submissions/{sub['id']}/assignments",
        json={"reviewer_id": 999_999},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 400


async def test_assign_reviewer_rejected_on_terminal_status(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    """accepted / rejected 是终态，不能再分配审稿人。"""
    sub = await _create_submission(client, test_user)
    reviewer = await _register(client, "rev_three", "rev3@example.com")

    decision = await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "reject", "editor_note": "not a fit"},
        headers=auth_headers(admin_user),
    )
    assert decision.status_code == 200

    response = await client.post(
        f"/api/submissions/{sub['id']}/assignments",
        json={"reviewer_id": reviewer["user_id"]},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 400


async def test_admin_lists_and_cancels_assignment(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)
    reviewer = await _register(client, "rev_four", "rev4@example.com")

    created = await client.post(
        f"/api/submissions/{sub['id']}/assignments",
        json={"reviewer_id": reviewer["user_id"]},
        headers=auth_headers(admin_user),
    )
    assignment_id = created.json()["id"]

    listed = await client.get(
        f"/api/submissions/{sub['id']}/assignments", headers=auth_headers(admin_user)
    )
    assert listed.status_code == 200
    assert [a["id"] for a in listed.json()["data"]] == [assignment_id]

    cancelled = await client.delete(
        f"/api/submissions/{sub['id']}/assignments/{assignment_id}",
        headers=auth_headers(admin_user),
    )
    assert cancelled.status_code in (200, 204)


# ---------------------------------------------------------------------------
# B. 单盲：审稿报告按角色剥离
# ---------------------------------------------------------------------------


async def _completed_report(db_session: object, submission_id: int, tenant_id: object) -> int:
    """把该 submission 的分配标为 completed 并插入一份报告，返回 assignment_id。"""
    result = await db_session.execute(  # type: ignore[attr-defined]
        select(ReviewAssignment).where(ReviewAssignment.submission_id == submission_id)
    )
    assignment = result.scalars().first()
    assert assignment is not None
    assignment.status = "completed"
    db_session.add(  # type: ignore[attr-defined]
        ReviewReport(
            tenant_id=assignment.tenant_id,
            assignment_id=assignment.id,
            recommendation="minor_revision",
            scores={"originality": 4, "clarity": 3},
            comments_to_author="Please clarify section 3.",
            comments_to_editor="Reviewer suspects the data is thin.",  # editor-only
            submitted_at=datetime.now(UTC),
        )
    )
    await db_session.commit()  # type: ignore[attr-defined]
    return assignment.id


async def test_author_sees_report_without_editor_comments(
    client: AsyncClient, test_user: dict, admin_user: dict, db_session: object
) -> None:
    """单盲核心断言：作者可见 comments_to_author，但 comments_to_editor 必须为 None。"""
    sub = await _create_submission(client, test_user)
    reviewer = await _register(client, "rev_five", "rev5@example.com")
    await client.post(
        f"/api/submissions/{sub['id']}/assignments",
        json={"reviewer_id": reviewer["user_id"]},
        headers=auth_headers(admin_user),
    )
    await _completed_report(db_session, sub["id"], None)

    response = await client.get(
        f"/api/submissions/{sub['id']}/reports", headers=auth_headers(test_user)
    )
    assert response.status_code == 200
    reports = response.json()
    assert len(reports) == 1
    assert reports[0]["comments_to_author"] == "Please clarify section 3."
    assert reports[0]["comments_to_editor"] is None


async def test_editor_sees_full_report_including_editor_comments(
    client: AsyncClient, test_user: dict, admin_user: dict, db_session: object
) -> None:
    sub = await _create_submission(client, test_user)
    reviewer = await _register(client, "rev_six", "rev6@example.com")
    await client.post(
        f"/api/submissions/{sub['id']}/assignments",
        json={"reviewer_id": reviewer["user_id"]},
        headers=auth_headers(admin_user),
    )
    await _completed_report(db_session, sub["id"], None)

    response = await client.get(
        f"/api/submissions/{sub['id']}/reports", headers=auth_headers(admin_user)
    )
    assert response.status_code == 200
    assert response.json()[0]["comments_to_editor"] == "Reviewer suspects the data is thin."


async def test_unrelated_user_cannot_read_reports(
    client: AsyncClient, test_user: dict, admin_user: dict, db_session: object
) -> None:
    sub = await _create_submission(client, test_user)
    reviewer = await _register(client, "rev_seven", "rev7@example.com")
    await client.post(
        f"/api/submissions/{sub['id']}/assignments",
        json={"reviewer_id": reviewer["user_id"]},
        headers=auth_headers(admin_user),
    )
    await _completed_report(db_session, sub["id"], None)

    outsider = await _register(client, "outsider", "outsider@example.com")
    response = await client.get(
        f"/api/submissions/{sub['id']}/reports", headers=auth_headers(outsider)
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# C. 编辑决断
# ---------------------------------------------------------------------------


async def test_editor_decision_major_revision(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)

    response = await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "major_revision", "editor_note": "needs more experiments"},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "major_revision"
    assert body["editor_note"] == "needs more experiments"
    assert body["reviewed_by"] == admin_user["user_id"]


async def test_editor_decision_accept_materializes_resource(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)

    response = await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "accept"},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["resource_id"] is not None


async def test_editor_decision_requires_editor(client: AsyncClient, test_user: dict) -> None:
    sub = await _create_submission(client, test_user)

    response = await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "accept"},
        headers=auth_headers(test_user),
    )
    assert response.status_code == 403


async def test_editor_decision_rejects_unknown_decision(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)

    response = await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "maybe"},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 422  # pydantic enum 校验在业务分支之前拦下


async def test_editor_decision_rejected_on_terminal_status(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)
    await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "reject"},
        headers=auth_headers(admin_user),
    )

    response = await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "accept"},
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# D. 作者重投 + 版本历史
# ---------------------------------------------------------------------------


async def test_author_resubmit_creates_new_version(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)
    await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "minor_revision"},
        headers=auth_headers(admin_user),
    )

    response = await client.post(
        f"/api/submissions/{sub['id']}/resubmit",
        json={"note": "按意见补充了实验"},
        headers=auth_headers(test_user),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "under_review"

    versions = await client.get(
        f"/api/submissions/{sub['id']}/versions", headers=auth_headers(test_user)
    )
    assert versions.status_code == 200
    # 版本历史按版本号倒序返回：v1 初稿 + v2 本次重投快照
    rows = versions.json()["data"]
    assert sorted(v["version"] for v in rows) == [1, 2]
    latest = next(v for v in rows if v["version"] == 2)
    assert latest["note"] == "按意见补充了实验"


async def test_resubmit_by_non_author_forbidden(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)
    await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "minor_revision"},
        headers=auth_headers(admin_user),
    )
    other = await _register(client, "other_author", "other@example.com")

    response = await client.post(
        f"/api/submissions/{sub['id']}/resubmit", json={}, headers=auth_headers(other)
    )
    assert response.status_code == 403


async def test_resubmit_rejected_in_pending_status(client: AsyncClient, test_user: dict) -> None:
    """pending 尚未进入返修，不能直接重投。"""
    sub = await _create_submission(client, test_user)

    response = await client.post(
        f"/api/submissions/{sub['id']}/resubmit", json={}, headers=auth_headers(test_user)
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# E. 稿件文件上传 / 下载
# ---------------------------------------------------------------------------

_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"


async def test_author_uploads_and_downloads_manuscript(
    client: AsyncClient, test_user: dict
) -> None:
    sub = await _create_submission(client, test_user)

    uploaded = await client.post(
        f"/api/submissions/{sub['id']}/files",
        files={"file": ("manuscript.pdf", _PDF, "application/pdf")},
        headers=auth_headers(test_user),
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["file_path"]

    downloaded = await client.get(
        f"/api/submissions/{sub['id']}/files", headers=auth_headers(test_user)
    )
    assert downloaded.status_code == 200
    assert downloaded.content == _PDF


async def test_upload_by_non_author_forbidden(client: AsyncClient, test_user: dict) -> None:
    sub = await _create_submission(client, test_user)
    other = await _register(client, "uploader", "uploader@example.com")

    response = await client.post(
        f"/api/submissions/{sub['id']}/files",
        files={"file": ("m.pdf", _PDF, "application/pdf")},
        headers=auth_headers(other),
    )
    assert response.status_code == 403


async def test_upload_rejects_disallowed_mime(client: AsyncClient, test_user: dict) -> None:
    sub = await _create_submission(client, test_user)

    response = await client.post(
        f"/api/submissions/{sub['id']}/files",
        files={"file": ("evil.sh", b"#!/bin/sh", "application/x-sh")},
        headers=auth_headers(test_user),
    )
    assert response.status_code == 400


async def test_upload_rejected_on_terminal_status(
    client: AsyncClient, test_user: dict, admin_user: dict
) -> None:
    sub = await _create_submission(client, test_user)
    await client.patch(
        f"/api/submissions/{sub['id']}/decision",
        json={"decision": "reject"},
        headers=auth_headers(admin_user),
    )

    response = await client.post(
        f"/api/submissions/{sub['id']}/files",
        files={"file": ("m.pdf", _PDF, "application/pdf")},
        headers=auth_headers(test_user),
    )
    assert response.status_code == 400
