"""Public-facing privacy policy page.

GDPR Article 13 / 14 requires that data subjects be informed of the
controller's identity, the categories of data processed, the purposes
of processing, and the retention period before any personal data is
collected. We surface the policy document as a single endpoint so
that any client (SPA, mobile, curl) can fetch the canonical text
without having to bundle a copy at build time.

The text itself lives in ``PRIVACY_POLICY_MD`` so it can be updated
by an ops change without redeploying. The endpoint returns it as
``text/markdown`` so a browser renders it as plain text and a SPA
can convert it to HTML via a markdown library if it wants the
formatted view.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["public"])


PRIVACY_POLICY_MD = """\
# ScholarHub Privacy Policy

_Last updated: 2026-07-25_

## Who we are

ScholarHub ("we", "us") operates an academic literature platform.
Our contact for privacy enquiries is `privacy@scholarhub.example`.

## What data we collect

When you register an account we collect:

- Email address (used for login and password reset).
- Username (display name on your public profile).
- Password (stored as a bcrypt hash; we never see the cleartext).
- Time of account creation.

When you use the service we additionally collect:

- Books / articles you submit, annotate, or list.
- Reviews and ratings you write.
- Optional profile fields you choose to fill in (display name, bio).
- IP address and approximate request timing for security audit logs.
- HTTP cookies: a session refresh cookie (HttpOnly, SameSite=Strict)
  and, if enabled, a CSRF double-submit cookie.

We do **not** collect:

- Advertising identifiers.
- Third-party tracking pixels.
- Biometric data.
- Special-category data (race, religion, health, sexuality, etc.).

## What we use it for

- Providing the service (authentication, storing your library).
- Preventing abuse (rate limiting, brute-force protection).
- Auditing account actions for 365 days so you have a record of who
  accessed your data and when.
- Complying with legal obligations.

## Legal basis

For users in the EEA / UK we rely on Article 6(1)(b) — performance
of a contract — for the authentication and library data, and on
Article 6(1)(f) — legitimate interests — for security audit logs.

## How long we keep it

- Account profile data: until you delete your account.
- After you delete your account: PII fields (email, username,
  password, TOTP secret) are anonymised in place immediately, and
  the row is hard-deleted after a **30-day grace window**.
- Audit logs: **365 days**.
- Backups: deleted within 90 days.

## Your rights

You can at any time:

- Download all data we hold about you (`GET /api/users/me/export`).
- Soft-delete your account (`DELETE /api/users/me`).
- Restore a soft-deleted account within the 30-day grace window
  (`POST /api/users/me/restore`).
- Disable two-factor authentication (`POST /api/auth/2fa/disable`).

For data-subject access requests that go beyond the self-service
endpoints above, email `privacy@scholarhub.example`. We respond
within 30 days as required by Article 12(3).

## How we protect it

- All traffic is served over HTTPS in production.
- Passwords are bcrypt-hashed with a per-deployment salt.
- JWT access tokens are short-lived (15 minutes) and revocable via
  a per-user token version counter.
- Refresh tokens are rotated on every use; replay of a consumed
  refresh token is refused.
- Two-factor authentication (TOTP) is available and recommended.
- Rate limiting rejects brute-force attempts at the proxy layer.
- Audit logs are tamper-evident: each row records the actor, the
  target, the action, and the timestamp.

## Changes to this policy

Material changes are announced on the project blog at least 14 days
before they take effect. The "Last updated" date above is the source
of truth.
"""


@router.get("/privacy", response_class=PlainTextResponse, include_in_schema=False)
async def get_privacy_policy() -> str:
    """Return the privacy policy as plain text / markdown."""
    return PRIVACY_POLICY_MD
