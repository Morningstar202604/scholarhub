<div align="center">

<img src="docs/assets/logo.svg" alt="ScholarHUB logo" width="120" height="120" />

# ScholarHUB

[English](README.md) · [中文](README.zh.md) · [日本語](README.ja.md)

### Stop rebuilding the journal from scratch.

**An open-source backbone that ships the entire academic publishing loop — submit, review, publish, read — in one codebase.**

> 11 backend modules · 644 tests at 84% coverage · 66 end-to-end specs · strict typing end to end

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache_2.0-blue.svg?style=flat-square&logo=opensourceinitiative&logoColor=white)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.2.0-6B7280?style=flat-square)](VERSION)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB.svg?logo=python&logoColor=white&style=flat-square)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white&style=flat-square)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=white&style=flat-square)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6.svg?logo=typescript&logoColor=white&style=flat-square)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1.svg?logo=postgresql&logoColor=white&style=flat-square)](https://www.postgresql.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4.svg?logo=tailwindcss&logoColor=white&style=flat-square)](https://tailwindcss.com/)
[![Docker](https://img.shields.io/badge/Docker--Compose-2496ED.svg?logo=docker&logoColor=white&style=flat-square)](https://docs.docker.com/compose/)

[![Modules](https://img.shields.io/badge/modules-11-6366F1?style=flat-square)](ARCHITECTURE.md)
[![Unit tests](https://img.shields.io/badge/unit_tests-644-10B981?style=flat-square&logo=pytest&logoColor=white)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-84%25-2C5AA0?style=flat-square)](#testing)
[![E2E](https://img.shields.io/badge/E2E_specs-66-22C55E?style=flat-square&logo=playwright&logoColor=white)](#testing)
[![Mypy](https://img.shields.io/badge/mypy-strict-0E7490?style=flat-square&logo=python&logoColor=white)](#testing)
[![Status](https://img.shields.io/badge/status-pre--alpha-F59E0B?style=flat-square)](#status)

**[Why](#why-scholarhub) · [What's inside](#whats-inside) · [Architecture](#architecture) · [Quick start](#quick-start) · [Testing](#testing) · [Docs](#docs) · [Contributing](#contributing)**

</div>

---

## Why ScholarHUB

Most teams rebuild the same journal scaffold from scratch — submission forms, reviewer assignment, a CMS for published papers. ScholarHUB ships that scaffold as a **real, multi-role product** instead of yet another custom CMS:

- **One platform, four roles.** Authors submit; editors assign and decide; reviewers report; readers browse, read, and follow. No glue code between disconnected systems.
- **The full loop, not a demo.** Manuscript metadata, single/double-blind review, versioned revisions, DOI registration, catalog, in-browser reading with cross-device progress, subscriptions, and recommendations — all wired together.
- **Secure by default.** Passkeys (WebAuthn) and TOTP two-factor, JWT with a server-side denylist and key rotation, captcha on signup, and a per-action audit log.
- **Self-hostable in minutes.** `docker compose up` on a single node; PostgreSQL for production, SQLite for dev and CI.

### The whole loop in one picture

<div align="center">
<img src="docs/assets/workflow.svg" alt="Submit → review → publish → read workflow" width="900" />
</div>

### See it running

<div align="center">

<a href="docs/assets/demo/ScholarHUB-promo.mp4">
<img src="docs/assets/screenshots-overview.png" alt="ScholarHUB interface overview — catalog, review workbench, recommendations, library, reader" width="900" />
</a>

**▶ [Watch the 60-second tour](docs/assets/demo/ScholarHUB-promo.mp4)** · [full walkthrough](docs/assets/demo/ScholarHUB-walkthrough.mp4) · [all 19 screenshots](docs/assets/screenshots)

</div>

## What's inside

| Capability | Highlights |
|---|---|
| **Submissions & review** | Full metadata intake, single/double-blind workflows, reviewer assignment, versioned revisions, editor decisions, terminal-state guards |
| **Publication & catalog** | Volume/issue management, searchable published catalog, DOI registration via DataCite |
| **Metadata ingest** | Pull authoritative records from Crossref, arXiv, PubMed, OpenAlex, and Semantic Scholar — plus BibTeX / RIS / CSV import |
| **Reader experience** | In-browser PDF reader, reading-progress sync across devices, personal reading lists, follow authors & subjects |
| **Auth & security** | WebAuthn passkeys, TOTP 2FA, JWT denylist + key rotation, captcha, RBAC (author / editor / reviewer / reader / admin) |
| **Multi-tenant** | Host multiple journals on one deployment with host-based tenant resolution and cached routing |
| **Discovery** | Follow graphs, recommendations, email + in-app notifications, citation export (BibTeX / RIS / CSL) |

Every domain capability is an independent module — disable, replace, or extend it without touching core.

## Architecture

<div align="center">
<img src="docs/assets/architecture.svg" alt="ScholarHUB architecture" width="820" />
</div>

- **Backend** — FastAPI (async), SQLAlchemy 2.0 async, PostgreSQL / SQLite, modular `app/modules/*` with strict `mypy` and `ruff`.
- **Frontend** — React 19 + TanStack Router + TypeScript 5.9 + Tailwind v4 + shadcn/ui, type-safe end to end.
- **Tests** — `pytest` (parallel, 84% line coverage, `--cov-fail-under=80`), `vitest` for the frontend, Playwright for the full submit → review → publish → read journey.

### Two defenses worth knowing

- **Two-layer tenant isolation.** Every domain table carries a `tenant_id`. The app appends the filter on every query, and PostgreSQL Row-Level Security rejects cross-tenant rows even if the app forgets — defense in depth, not a hope.
- **Module registry.** `app.core.modules.load_all()` loads modules in dependency order, registers their ORM tables, mounts their routes, and adds health checks. New capability = one entry, zero core changes.

## Quick start

### Option 1 — Docker Compose (recommended)

```bash
# 1. Generate strong secrets
echo "SCHOLARHUB_SECRET_KEY=$(openssl rand -hex 32)" > .env
echo "SCHOLARHUB_ADMIN_PASSWORD=$(openssl rand -base64 18)" >> .env

# 2. Start the dev stack (Postgres + backend + frontend)
docker compose -f infra/docker-compose.yml up --build

# 3. Open the API docs and the SPA
xdg-open http://localhost:8000/docs
xdg-open http://localhost:5173
```

### Option 2 — Local bare metal (development)

Requires Python 3.12+, Node 20+, and a PostgreSQL 17 instance.

```bash
# Backend
cd apps/backend && uv sync && uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Frontend (another terminal)
cd apps/frontend && npm install && npm run dev
```

### Option 3 — Production

```bash
cp .env .env.prod                 # fill at least SCHOLARHUB_SECRET_KEY + SCHOLARHUB_ADMIN_PASSWORD
# edit infra/Caddyfile -> replace scholarhub.example.com with your domain
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod up -d --build
```

> Mail (Mailgun / SendGrid / SES / Postmark) and OIDC SSO (Google / GitHub / Keycloak): see [integrations.md](docs/integrations.md).

## Tech stack

Every choice is mainstream and long-term hostable — no exotic dependencies.

| Layer | Backend | Frontend |
|---|---|---|
| Language / framework | Python 3.12+, FastAPI 0.115+ | React 19, TypeScript 5.9, Vite 7 |
| Data | SQLAlchemy 2 (async), Alembic, PostgreSQL 17 | TanStack Router v1, TanStack Query v5, Zustand |
| Validation / auth | Pydantic 2, JWT + bcrypt, PyJWT, authlib (OIDC) | shadcn/ui + Radix, Tailwind v4, lucide-react |
| Infra | Docker Compose, Caddy (auto TLS), structlog | Playwright (E2E) |
| Toolchain | uv, ruff, mypy (strict), pytest, bandit | ESLint, Vitest, tsc project references |

All variables are prefixed `SCHOLARHUB_`. The full list and the `.env` template live in [`apps/backend/app/core/config.py`](apps/backend/app/core/config.py) and [`apps/backend/.env.example`](apps/backend/.env.example). Essentials: `SCHOLARHUB_SECRET_KEY`, `SCHOLARHUB_ADMIN_PASSWORD`, `SCHOLARHUB_DATABASE_URL`, `SCHOLARHUB_TENANCY_MODE` (`single` / `multi`), `SCHOLARHUB_ENVIRONMENT`.

## Security

Defense in depth is enabled the moment the backend boots:

- **Auth** — bcrypt hashing; short-lived JWT access + httpOnly refresh cookie + per-user `token_version`.
- **2FA (TOTP)** — RFC 6238, per-user secret Fernet-encrypted at rest, 10 single-use backup codes (SHA-256).
- **Passkeys** — WebAuthn registration / authentication state machine with one-time, TTL-bound challenges.
- **JWT key rotation** — ordered key chain; `POST /api/admin/reload-secret-keys` rotates with zero downtime.
- **Rate limit** — sliding window per IP + route; `RedisRateLimiterStore` when `SCHOLARHUB_REDIS_URL` is set, otherwise in-memory (Redis errors auto-fail-open).
- **GDPR** — export / soft-delete (30-day grace) / restore self-service endpoints.
- **Headers & errors** — CSP, HSTS, CSRF double-submit; RFC 7807 `application/problem+json` everywhere; per-tenant audit log on every privileged action.

See [SECURITY.md](SECURITY.md) for the full policy and threat model.

## Default roles

`core` creates these on startup (assignable from the admin shell):

| Role | Scope |
|---|---|
| `admin` | Full access — admin shell, user management, audit log |
| `editor` | Assign reviewers, organize volumes/issues, accept/reject, push to *published* |
| `reviewer` | View assigned submissions, file review reports |
| `author` | Submit manuscripts, view own status, upload revisions |
| `member` | Read, save, follow, view recommendations |

## Testing

Quality is enforced in CI, not just claimed:

- **Backend** — **644** `pytest` cases at **84% line coverage** with a hard `--cov-fail-under=80` gate; `mypy --strict` and `ruff` clean.
- **Frontend** — `vitest` unit + component tests under strict `tsc` (**100** cases).
- **E2E** — **66 Playwright specs** exercising the real submit → review → publish → read workflow against a spawned test server (no flaky production parity).
- **CI** — backend, frontend, and e2E jobs on every push; strict pytest markers; a version-consistency guard keeps `VERSION` / `pyproject` / `package.json` / `__version__` in lockstep.

```bash
# Backend
cd apps/backend && uv run ruff check . && uv run mypy app && uv run pytest -q

# Frontend
cd apps/frontend && npm run lint && npm run typecheck && npm run test

# E2E (Playwright spawns both servers via E2E_SPAWN_SERVER=1)
cd apps/frontend && E2E_SPAWN_SERVER=1 npx playwright test
```

## Docs

- [Architecture](ARCHITECTURE.md) · [Deployment](DEPLOYMENT.md) · [Integrations](docs/integrations.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Code of Conduct](CODE_OF_CONDUCT.md) · [Changelog](CHANGELOG.md)

## Contributing

Issues and PRs are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for branch naming, commit conventions, and the PR checklist.

## Repository

| Platform | URL | Role |
|---|---|---|
| GitCode | <https://gitcode.com/badhope/scholarhub> | Primary |
| Gitee | <https://gitee.com/badhope/scholarhub> | Mirror |
| GitHub | <https://github.com/x33834/scholarhub> | Mirror |

All remotes are kept in sync (same branches, tags, and HEAD).

## License

Copyright © 2026 Morningstar202604. Released under the [Apache-2.0 License](LICENSE). Provided "as is", without warranty of any kind.
