# Security Policy

## Supported Versions

Only the latest release on `main` receives security updates.

## Reporting a Vulnerability

If you discover a security vulnerability, **do not open a public issue**.

Report it privately:

- Email: **badhope@noreply.gitcode.com**
- Or use the repository's private security advisory feature

Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive a response within 72 hours. Please allow up to 30 days for a
fix before public disclosure.

## Built-in Security Measures

ScholarHub ships with the following defense-in-depth layers:

- **Two-layer tenant isolation** — every domain table carries `tenant_id`; the
  application layer appends the filter to every query, and PostgreSQL Row Level
  Security (RLS) enforces it again at the database level via
  `SET LOCAL app.current_tenant_id`.
- **JWT auth with refresh token rotation** — short-lived access tokens, httpOnly
  refresh cookies, rotation version on every refresh.
- **OIDC SSO** via authlib (Google / GitHub / Generic / Keycloak).
- **Rate limiting** — sliding-window in-memory limiter per client IP and route.
- **Security headers middleware** — CSP, HSTS, X-Frame-Options, X-Content-Type,
  Referrer-Policy, Permissions-Policy.
- **Password hashing** — bcrypt with per-row salt.
- **Audit log** — every privileged admin action is recorded per tenant.

## Local Security Tooling

Optional, run manually:

```bash
cd apps/backend
uv run bandit -r app
uv run pip-audit
uv run ruff check .
uv run mypy app
```

The frontend has its own checks:

```bash
cd apps/frontend
npm run lint
npm run typecheck
```

## Disclaimer

This software is provided "as is" without warranty. The maintainer is not
liable for any damages arising from the use of this software.
