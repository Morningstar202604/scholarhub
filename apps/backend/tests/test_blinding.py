"""Tests for double-blind review mode.

Contract:
- Default is single-blind: reviewers see full author info (backwards
  compatible with every existing deployment — no migration needed).
- Admin can read/switch the mode via /admin/settings/review-mode
  (audited); invalid values are rejected by schema validation.
- Under double-blind, a non-admin reviewer's submission view has
  authors / corresponding email / submitted_by / venue / doi scrubbed,
  while all academic content (title/abstract/keywords) stays intact.
- Admin reviewers are exempt (platform operators can always debug).
- Author-side blinding (author never sees reviewer identity) is already
  covered by test_review.py's single-blind report tests.
"""

from __future__ import annotations

from conftest import auth_headers
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Tenant
from app.modules.review.blinding import ANONYMIZED_AUTHOR

_PAYLOAD = {
    "title": "Double-Blind Test Paper",
    "type": "paper",
    "authors": ["Alice Identifiable", "Bob Traceable"],
    "year": 2024,
    "discipline": "computer science",
    "tags": ["blinding"],
    "abstract": "Abstract for the double-blind test.",
    "preview": "Preview text.",
    "venue": "Identifiable University Workshop",
    "doi": "10.9999/blind.test.001",
    "keywords": ["anonymity"],
    "corresponding_author_email": "alice@identifiable-university.edu",
}


async def _register(client: AsyncClient, tag: str) -> dict:
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": f"{tag}@example.org",
            "username": tag,
            "password": "password123",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return {"token": data["access_token"], "user_id": data["user_id"]}


async def _grant_reviewer(db_session: AsyncSession, user_id: int) -> None:
    from app.models import Role, UserRole

    tenant = (
        await db_session.execute(select(Tenant).where(Tenant.slug == "default"))
    ).scalar_one()
    role = (
        await db_session.execute(
            select(Role).where(Role.tenant_id == tenant.id, Role.name == "reviewer")
        )
    ).scalar_one_or_none()
    if role is None:
        role = Role(tenant_id=tenant.id, name="reviewer", description="test")
        db_session.add(role)
        await db_session.flush()
    db_session.add(UserRole(tenant_id=tenant.id, user_id=user_id, role_id=role.id))
    await db_session.commit()


async def _setup(
    client: AsyncClient, admin_user: dict, test_user: dict, db_session: AsyncSession
) -> dict:
    """作者投稿 → 注册独立审稿人 → 授角色 → 指派。"""
    created = await client.post(
        "/api/submissions", json=_PAYLOAD, headers=auth_headers(test_user)
    )
    created.raise_for_status()
    submission = created.json()

    reviewer = await _register(client, "blindreviewer")
    await _grant_reviewer(db_session, int(reviewer["user_id"]))

    assigned = await client.post(
        f"/api/submissions/{submission['id']}/assignments",
        json={"reviewer_id": reviewer["user_id"]},
        headers=auth_headers(admin_user),
    )
    assigned.raise_for_status()
    return {
        "submission": submission,
        "assignment": assigned.json(),
        "reviewer": reviewer,
    }


async def _set_mode(client: AsyncClient, admin_user: dict, mode: str) -> None:
    resp = await client.patch(
        "/api/admin/settings/review-mode",
        json={"review_mode": mode},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    assert resp.json()["review_mode"] == mode


# ---------------------------------------------------------------------------
# Settings endpoint
# ---------------------------------------------------------------------------


async def test_default_mode_is_single_blind(
    client: AsyncClient, admin_user: dict
) -> None:
    resp = await client.get(
        "/api/admin/settings/review-mode", headers=auth_headers(admin_user)
    )
    assert resp.status_code == 200
    assert resp.json()["review_mode"] == "single_blind"


async def test_switch_mode_roundtrip_and_audited(
    client: AsyncClient, admin_user: dict
) -> None:
    await _set_mode(client, admin_user, "double_blind")
    resp = await client.get(
        "/api/admin/settings/review-mode", headers=auth_headers(admin_user)
    )
    assert resp.json()["review_mode"] == "double_blind"
    # 切换动作必须留审计
    logs = await client.get(
        "/api/admin/audit-logs?limit=10", headers=auth_headers(admin_user)
    )
    actions = [entry["action"] for entry in logs.json()]
    assert "admin.settings.review_mode" in actions
    # 切回
    await _set_mode(client, admin_user, "single_blind")


async def test_invalid_mode_rejected(client: AsyncClient, admin_user: dict) -> None:
    resp = await client.patch(
        "/api/admin/settings/review-mode",
        json={"review_mode": "triple_blind"},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 422


async def test_settings_require_admin(client: AsyncClient, test_user: dict) -> None:
    resp = await client.get(
        "/api/admin/settings/review-mode", headers=auth_headers(test_user)
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Reviewer-facing anonymization
# ---------------------------------------------------------------------------


async def test_single_blind_reviewer_sees_authors(
    client: AsyncClient, admin_user: dict, test_user: dict, db_session: AsyncSession
) -> None:
    """默认（单盲）：审稿人看得到作者。守住向后兼容。"""
    setup = await _setup(client, admin_user, test_user, db_session)
    resp = await client.get(
        f"/api/review/assignments/{setup['assignment']['id']}/submission",
        headers={"Authorization": f"Bearer {setup['reviewer']['token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["authors"] == _PAYLOAD["authors"]
    assert body["corresponding_author_email"] == _PAYLOAD["corresponding_author_email"]


async def test_double_blind_scrubs_identity_keeps_content(
    client: AsyncClient, admin_user: dict, test_user: dict, db_session: AsyncSession
) -> None:
    """双盲：身份字段被抹掉，学术内容原样保留。"""
    setup = await _setup(client, admin_user, test_user, db_session)
    await _set_mode(client, admin_user, "double_blind")

    resp = await client.get(
        f"/api/review/assignments/{setup['assignment']['id']}/submission",
        headers={"Authorization": f"Bearer {setup['reviewer']['token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # 身份字段全部被抹
    assert body["authors"] == [ANONYMIZED_AUTHOR]
    assert body["corresponding_author_email"] is None
    assert body["submitted_by"] is None
    assert body["venue"] is None
    assert body["doi"] is None
    # 学术内容完好
    assert body["title"] == _PAYLOAD["title"]
    assert body["abstract"] == _PAYLOAD["abstract"]
    assert body["keywords"] == _PAYLOAD["keywords"]

    await _set_mode(client, admin_user, "single_blind")


async def test_double_blind_admin_exempt(
    client: AsyncClient, admin_user: dict, test_user: dict, db_session: AsyncSession
) -> None:
    """admin 以审稿人身份查看时不剥离（平台运营需要能排障）。"""
    created = await client.post(
        "/api/submissions", json=_PAYLOAD, headers=auth_headers(test_user)
    )
    created.raise_for_status()
    assigned = await client.post(
        f"/api/submissions/{created.json()['id']}/assignments",
        json={"reviewer_id": admin_user["user_id"]},
        headers=auth_headers(admin_user),
    )
    assigned.raise_for_status()
    await _set_mode(client, admin_user, "double_blind")

    resp = await client.get(
        f"/api/review/assignments/{assigned.json()['id']}/submission",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    assert resp.json()["authors"] == _PAYLOAD["authors"]

    await _set_mode(client, admin_user, "single_blind")
