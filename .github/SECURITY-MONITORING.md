# Security monitoring — ScholarHub

This file describes the security automation that protects the `scholarhub`
repository and how to operate it.

## Layers

| Layer | Tool | What it does | Where to look |
|-------|------|-------------|---------------|
| 1. Secret scanning | [Gitleaks](https://github.com/gitleaks/gitleaks) | Pre-commit + GitHub Action blocks commit/push of API keys, JWT secrets, DB passwords | `.gitleaks.toml`, `.github/workflows/ci.yml` job `secrets-scan` |
| 2. Dependency audit | [pip-audit](https://pypi.org/project/pip-audit/) | PyPI deps CVE scan on every CI run | `.github/workflows/ci.yml` job `backend` step `pip-audit` |
| 3. Static SAST | [CodeQL](https://codeql.github.com/) | SQLi, XSS, deserialization, weak crypto detection for Python + JS/TS | `.github/workflows/ci.yml` job `codeql` |
| 4. Linter | [Ruff](https://docs.astral.sh/ruff/) + [ESLint](https://eslint.org/) | Style + many bug categories (B-prefix rules) | `apps/backend/pyproject.toml [tool.ruff]`, `apps/frontend/eslint.config.*` |
| 5. Typecheck | [mypy](https://mypy.readthedocs.io/) strict + [tsc](https://www.typescriptlang.org/) strict | Catches API misuse, missing null checks, type confusion | `apps/backend/pyproject.toml [tool.mypy]`, `apps/frontend/tsconfig.json` |
| 6. Dependabot | [Dependabot](https://docs.github.com/en/code-security/dependabot) | Daily PRs for vulnerable/outdated deps | `.github/dependabot.yml` |
| 7. Auto-merge | Dependabot workflow | Auto-squash-merge patch & minor updates | `.github/workflows/dependabot-auto-merge.yml` |

## Manual checks (run before every release)

```bash
# 1. Secret scan (local, mirrors CI)
docker run --rm -v "$PWD:/pwd" zricethezav/gitleaks:latest detect \
    --source /pwd --config /pwd/.gitleaks.toml -v

# 2. PyPI vulnerabilities
cd apps/backend && uv run pip-audit

# 3. Python bandit (fast security lint)
cd apps/backend && uv run bandit -r app -lll

# 4. Full test + lint
cd apps/backend && uv run ruff check . && uv run mypy app && uv run pytest
cd apps/frontend && npm run lint && npm run typecheck && npm test && npm run build
```

## Secrets inventory (what the repo must NEVER see)

| Secret | Env var | Why |
|--------|---------|-----|
| JWT signing key | `SCHOLARHUB_SECRET_KEY` | Allows forging any user session token |
| Previous JWT keys | `SCHOLARHUB_PREVIOUS_SECRET_KEYS` | Same risk, used during rotation windows |
| Database URL with password | `SCHOLARHUB_DATABASE_URL` | Full DB access; cascades to all PII |
| Redis URL with password | `SCHOLARHUB_REDIS_URL` | Rate-limit + cache poisoning + session theft |
| OIDC client secret | `SCHOLARHUB_OIDC_*_CLIENT_SECRET` | Allows impersonation via the configured IdP |
| Admin bootstrap password | `SCHOLARHUB_ADMIN_PASSWORD` | First-boot superuser; instant full takeover |
| SMTP password | `SCHOLARHUB_SMTP_PASSWORD` (Phase 10+) | Used to send password-reset mails |

## Incident response

If a secret leaks:

1. **Rotate immediately.** Treat the leaked value as public; it cannot
   be "unleaked". Update `SCHOLARHUB_SECRET_KEY` in every env,
   push via `POST /api/admin/reload-secret-keys` so existing tokens
   are invalidated through the rotation window.
2. **Audit access.** Use `GET /api/audit-logs` (admin) to look for
   anomalous logins between leak and rotation.
3. **Notify.** Open a GitHub Security Advisory
   ([Security tab → Advisories → New draft security advisory](https://github.com/weed33834/scholarhub/security/advisories/new)).
4. **Force re-auth.** Bump `token_version` on affected users
   via `PATCH /api/admin/users/{id}` so all sessions die.