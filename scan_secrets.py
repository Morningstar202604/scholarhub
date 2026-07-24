"""Quick secret-pattern scan across the repo (excluding venvs, build output).

Run: python scan_secrets.py
Prints findings to stdout; exits 0 on CLEAN, 1 on findings.
"""
from __future__ import annotations

import os
import re

PATTERNS = {
    "ghp_": re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    "gho_": re.compile(r"gho_[A-Za-z0-9]{20,}"),
    "pkcs8-pem": re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    "aws-ak": re.compile(r"AKIA[0-9A-Z]{16}"),
    "stripe-live": re.compile(r"sk_live_[A-Za-z0-9]{20,}"),
    "stripe-test": re.compile(r"sk_test_[A-Za-z0-9]{20,}"),
    "postgres-with-pw": re.compile(r"postgres(?:ql)?://[^\s/:@]+:[^\s/:@]+@"),
    "redis-with-pw": re.compile(r"redis://[^/\s]+:[^/\s@]+@"),
    "slack-bot": re.compile(r"xoxb-[A-Za-z0-9-]{20,}"),
}

# Only scan source dirs we own — skip venvs, builds, caches, .git.
SCAN_ROOTS = [
    "apps/backend/app",
    "apps/backend/tests",
    "apps/backend/alembic",
    "apps/backend/uv.lock",
    "apps/backend/pyproject.toml",
    "apps/frontend/src",
    "apps/frontend/package.json",
    "apps/frontend/package-lock.json",
    "apps/frontend/vite.config.ts",
    "apps/frontend/.env.example",
    "apps/frontend/tsconfig.json",
    "infra",
    "docs",
    ".github",
    "scripts",
    ".",
]

SKIP_NAMES = {".venv", "node_modules", "dist", "build", "__pycache__", ".git",
              ".turbo", ".vite", ".vitest-cache", ".qclaw", "playwright-report",
              "test-results", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
             ".pdf", ".zip", ".tar", ".gz", ".woff", ".woff2", ".ttf",
             ".mp4", ".mp3", ".wav", ".ico"}
SKIP_SUFFIXES = ("-lock.json", "lock.yaml", "lock.toml")


def walk_scan(root: str):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune skip dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_NAMES]
        for fn in filenames:
            if any(fn.endswith(s) for s in SKIP_SUFFIXES):
                pass  # still scan
            full = os.path.join(dirpath, fn)
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_EXTS:
                continue
            try:
                if os.path.getsize(full) > 512_000:
                    continue
            except OSError:
                continue
            yield full


def main() -> int:
    hits = []
    for root in SCAN_ROOTS:
        if not os.path.exists(root):
            continue
        for path in walk_scan(root):
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
                text = raw.decode("utf-8", errors="ignore")
            except OSError:
                continue
            for name, pat in PATTERNS.items():
                for m in pat.finditer(text):
                    hits.append((path.replace("\\", "/"), name, m.group(0)[:80]))
    print(f"Found {len(hits)} hits", flush=True)
    for h in hits[:80]:
        print(h, flush=True)
    return 0 if not hits else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())