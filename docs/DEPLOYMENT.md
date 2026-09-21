# Deployment guide

This guide covers everything needed to take ScholarHUB from a fresh
server to a running production deployment, and answers the common
"do I need Cloudflare / a special cloud?" question.

The short version:

> **One VPS + one domain is enough.** Everything runs from
> `infra/docker-compose.prod.yml` (PostgreSQL 17, Meilisearch, FastAPI
> backend, static frontend, Caddy with automatic HTTPS). Cloudflare is
> optional — nice to have for CDN / origin hiding / Turnstile, never a
> hard requirement.

Two more deployment shapes exist besides this compose stack (see
[DEPLOY.md](../DEPLOY.md) for the full comparison):

- **Single container, single port** — `apps/backend/Dockerfile` is a
  multi-stage build that bakes the frontend `dist/` into the backend
  image (`deploy_server.py` serves SPA + API same-origin, no CORS) and
  runs `alembic upgrade head` automatically at startup. One service on
  any Docker PaaS (Render / Railway / Fly.io) runs the whole stack —
  point `SCHOLARHUB_DATABASE_URL` at a managed Postgres (e.g. Neon).
- **Root `docker-compose.yml` (VPS all-in-one)** — PostgreSQL 17 +
  backend + Caddy auto-HTTPS with persistent volumes and startup
  migrations; copy the root `.env.example`, fill secrets, `docker
  compose up -d --build`.

---

## 1. Prerequisites

### 1.1 Server

Any Linux box with Docker works — a bare VPS, a cloud VM, even a home
server with a public DNS record.

| Profile | vCPU | RAM | Disk | Fits |
|---|---|---|---|---|
| Minimum | 1 | 2 GB | 20 GB | Single instance, Postgres + Meili, few hundred users |
| Recommended | 2 | 4 GB | 40 GB | Comfortable default incl. Meilisearch indexing |
| Scaled | 4 | 8 GB | 40 GB+ | Larger catalogs, PDF-heavy storage, monitoring stack |

Notes:

- Disk size is mostly driven by **uploads** (PDF manuscripts). Keep the
  upload volume on a partition you can grow, or offload to S3-compatible
  object storage (§3.4).
- Multi-node is supported in principle (Redis-backed rate limiting and
  token denylist), but a single node is the tested path.

### 1.2 Software

- Docker Engine ≥ 24 and the compose v2 plugin (`docker compose version`)
- That is it — images pull the rest. Bare-metal installs (uv + Python
  3.12 + PostgreSQL 17) are documented in the README "Quick start",
  but Docker is the supported production path.

### 1.3 Domain

One DNS record (A/AAAA) pointing at the server, with ports **80 and
443 reachable from the public internet**. Caddy obtains and renews
Let's Encrypt certificates automatically — no cert tooling needed.

If the host is *not* publicly reachable (internal deployment), see the
`internal` TLS comment at the top of `infra/Caddyfile`.

### 1.4 Do I need Cloudflare / a cloud service?

**No.** The full stack is self-contained in Docker Compose. Where third
party services help:

| Concern | Required? | Options |
|---|---|---|
| HTTPS certificates | No | Caddy does it automatically (Let's Encrypt) |
| CDN / DDoS protection / hiding origin IP | Optional | Cloudflare free plan in front of the VPS |
| CAPTCHA on registration | Optional | Pluggable hook (`SCHOLARHUB_CAPTCHA_REQUIRED_FOR_REGISTRATION` + `SCHOLARHUB_CAPTCHA_VERIFIER` — a dotted path to your own Turnstile/hCaptcha verifier, see `app/core/captcha.py`) |
| Transactional email | **Effectively yes in production** | Any SMTP relay: Mailgun / SendGrid / SES / Postmark (§3.3) |
| Object storage for PDFs | No (local disk default) | S3 / R2 / MinIO via `SCHOLARHUB_STORAGE_BACKEND=s3` |
| Full-text search | No (falls back to SQL ILIKE) | Bundled Meilisearch container |
| Error monitoring | Optional | Sentry DSN |
| DOI minting | Optional | DataCite account + prefix |

Cloudflare specifics, if you choose to use it:

1. Move DNS to Cloudflare, proxy (orange-cloud) the record.
2. Set SSL mode to **Full (strict)** — Caddy still serves a valid cert,
   so no origin certificate is needed.
3. Websockets / SSE pass through fine; nothing special is required.
4. Optional: Cloudflare R2 doubles as the S3 storage backend
   (`SCHOLARHUB_S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com`).

---

## 2. First deployment (step by step)

```bash
# 1. Get the code
git clone https://gitcode.com/badhope/scholarhub.git
cd scholarhub

# 2. Create the production env file
cp .env.example .env
```

Fill in `.env` — the **required** fields, and the two you must adjust
for production:

```ini
SCHOLARHUB_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
SCHOLARHUB_FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
SCHOLARHUB_ADMIN_PASSWORD=<strong initial password — change it again after first login>
SCHOLARHUB_DATABASE_URL=postgresql+asyncpg://scholarhub:<db-password>@localhost:5432/scholarhub

SCHOLARHUB_ENVIRONMENT=production
SCHOLARHUB_CORS_ORIGINS=https://your.domain
SCHOLARHUB_ALLOWED_HOSTS=your.domain
SCHOLARHUB_JSON_LOGS=true
```

`SCHOLARHUB_ENVIRONMENT=production` enables weak-secret rejection — the
server refuses to boot with placeholder keys, so the four values above
must be real.

```bash
# 3. Point Caddy at your domain
sed -i 's/scholarhub.example.com/your.domain/' infra/Caddyfile

# 4. (Recommended) run migrations as a one-shot, then start the stack
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.prod.yml --env-file .env \
  run --rm backend alembic upgrade head
```

The backend image's default CMD runs `alembic upgrade head` before
serving, so step 4 is technically optional for the first boot — running
it explicitly keeps migrations a deliberate, observable act instead of a
side effect of startup.

Verify:

```bash
curl https://your.domain/api/health
# → {"status":"ok","version":"0.2.0",...}
```

Log in with the bootstrap admin (`admin` / `SCHOLARHUB_ADMIN_PASSWORD`)
and **change the password immediately** — the bootstrap exists only to
get a first admin into the database.

### What `docker-compose.prod.yml` starts

| Service | Image | Role |
|---|---|---|
| `postgres` | postgres:17-alpine | Primary datastore, RLS tenant isolation |
| `meilisearch` | getmeili/meilisearch:v1.12 | Full-text search index |
| `backend` | built from `infra/Dockerfile.backend` | FastAPI API (:8000, internal) |
| `frontend` | built from `infra/Dockerfile.frontend` | Static SPA behind nginx (internal) |
| `caddy` | caddy:2-alpine | Only public port (80/443), TLS, reverse proxy |

Postgres data lives in the named volume `pgdata`; Caddy certificates in
`caddy_data`. Neither is ephemeral — `docker compose down` keeps them,
`down -v` deletes them (that is the destructive one).

---

## 3. Production configuration that actually matters

### 3.1 Email (verification + password reset)

Registration sends verification mail, password reset sends reset links.
The `console` backend only prints those mails to stdout — fine for dev,
useless in production. Configure an SMTP relay:

```ini
SCHOLARHUB_EMAIL_BACKEND=smtp
SCHOLARHUB_EMAIL_SMTP_HOST=smtp.mailgun.org
SCHOLARHUB_EMAIL_SMTP_PORT=587
SCHOLARHUB_EMAIL_SMTP_USER=...
SCHOLARHUB_EMAIL_SMTP_PASSWORD=...
SCHOLARHUB_EMAIL_FROM_ADDRESS=noreply@your.domain
```

Set up SPF/DKIM/DMARC for the sending domain or the mails will land in
spam. This is the one integration where a third-party service is close
to mandatory — self-hosted MTMs routinely get IP-blocked.

### 3.2 Secrets & key rotation

- All secrets come from `.env`; nothing is baked into images.
- Rotating `SCHOLARHUB_SECRET_KEY`: put the old key in
  `SCHOLARHUB_PREVIOUS_SECRET_KEYS` (comma-separated) so tokens signed
  by it remain verifiable during the rollout window.
- `SCHOLARHUB_FERNET_KEY` encrypts TOTP secrets at rest — losing it
  locks every 2FA user out. Back it up with the database.

### 3.3 Storage of uploads

- Default: local disk (`SCHOLARHUB_STORAGE_PATH`), volume-mounted in
  the container.
- S3-compatible: set `SCHOLARHUB_STORAGE_BACKEND=s3` plus the
  `SCHOLARHUB_S3_*` block (AWS S3, Cloudflare R2, MinIO all work via
  `SCHOLARHUB_S3_ENDPOINT_URL`).

### 3.4 Search & scale

- Meilisearch is bundled and wired by default. If you drop the service,
  remove `SCHOLARHUB_MEILISEARCH_URL` and the backend falls back to SQL
  `ILIKE` search.
- Redis: single-node installs do not need it. Add
  `SCHOLARHUB_REDIS_URL` when you run multiple backend replicas (shared
  rate-limit counters + token denylist).

---

## 4. Operations

### 4.1 Upgrades

```bash
cd scholarhub
git pull
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.prod.yml --env-file .env \
  run --rm backend alembic upgrade head
```

Migrations are forward-only here; check `CHANGELOG.md` for
breaking-change notes between your version and the target version
before upgrading.

### 4.2 Backups (do this before the first real user, not after)

`infra/backup.sh` dumps Postgres (custom format) and archives the
upload directory; `infra/restore.sh` is its counterpart. Wire the
backup into cron on the host:

```cron
0 3 * * * cd /opt/scholarhub/infra && ./backup.sh --output-dir /var/backups/scholarhub
```

Store at least one copy off the server (object storage, another machine
— anything that survives the VPS provider losing your disk).

### 4.3 Logs & monitoring

- `SCHOLARHUB_JSON_LOGS=true` → structured logs, one JSON object per
  line, ready for `docker compose logs` consumption by any collector.
- `GET /api/health` is the container-level liveness probe; it reports
  app version and DB pool stats.
- The compose file ships commented-out Prometheus + Grafana services —
  uncomment, configure retention, `up -d` again when you outgrow
  eyeballing logs.

### 4.4 Security checklist (first hour)

- [ ] `.env` contains only real secrets; file is `chmod 600`
- [ ] Admin bootstrap password changed after first login
- [ ] Firewall: only 22 / 80 / 443 open (the app talks to Postgres and
      Meilisearch over the internal compose network; they are never
      published to the host)
- [ ] `SCHOLARHUB_CORS_ORIGINS` / `SCHOLARHUB_ALLOWED_HOSTS` pinned to
      the real domain (no wildcards)
- [ ] SSH hardened (keys only, no root password auth)
- [ ] `infra/backup.sh` scheduled, and one restore actually tested
- [ ] Optional but recommended: Cloudflare in front; wire a CAPTCHA
      verifier (`app/core/captcha.py`) if registration abuse is a concern

---

## 5. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Caddy keeps failing TLS | Ports 80/443 blocked, or DNS not propagated — `dig your.domain` must return the server IP |
| Backend exits at boot, logs mention weak secret | `SCHOLARHUB_ENVIRONMENT=production` rejects placeholder keys/`change-me` values — generate real ones |
| `502` from Caddy on `/api/*` | Backend still migrating or crashed — `docker compose logs backend` |
| Login works, SPA calls fail with CORS | `SCHOLARHUB_CORS_ORIGINS` does not include the exact scheme+host of the SPA |
| Mails never arrive | Console backend active, or sender domain lacks SPF/DKIM |
| Search returns no results | Meilisearch unhealthy, or index not rebuilt after bulk import — see `docs/integrations.md` |

---

## 6. FAQ

**Q: Can I deploy without Docker?**
Yes — README "Quick start" documents the bare-metal path (uv + system
PostgreSQL). You take on the TLS and process-management chores yourself
(systemd units + any reverse proxy).

**Q: Can I run multiple tenants on one deployment?**
That is the default design: tenants are rows, isolated by PostgreSQL
RLS, not by infrastructure. One server serves many tenants.

**Q: Does it need a GPU / heavy machine?**
No. The workload is CRUD + PDF streaming; the recommended 2C/4G box is
already generous.

**Q: Where do uploaded PDFs live?**
`SCHOLARHUB_STORAGE_PATH` on the backend container volume by default,
or your S3-compatible bucket when `SCHOLARHUB_STORAGE_BACKEND=s3`.
