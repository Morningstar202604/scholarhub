"""FastAPI application entrypoint.

Composes: lifespan (DB + modules) �?middleware (tenant, security, CORS) �?core routers �?module routers.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware as StarletteMiddleware
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from app import __version__
from app.api import admin, auth, gdpr, health, modules, privacy, two_factor, users
from app.api.metrics import router as metrics_router
from app.api.oidc import router as oidc_router
from app.core.bootstrap import run_bootstrap
from app.core.config import settings
from app.core.db import check_db_connection, dispose_engine
from app.core.logging import configure_logging, get_logger
from app.core.modules import load_all, registry
from app.core.rate_limit_store import close_rate_limiter_store
from app.core.tenant import TenantContextMiddleware
from app.middleware.csrf import CSRFMiddleware
from app.middleware.metrics import HTTPMetricsMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

configure_logging()
logger = get_logger("scholarhub.startup")


@retry(
    stop=stop_after_attempt(settings.db_startup_retries + 1),
    wait=wait_fixed(settings.db_startup_retry_delay),
    retry=retry_if_exception_type(Exception),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _verify_db_with_retry() -> None:
    """Verify DB connectivity; tenacity retries up to ``db_startup_retries`` times."""
    await check_db_connection()
    logger.info("database_connection_verified")


# Load enabled modules eagerly so their routers are available when the
# app is constructed. Module __init__ only registers manifests (no I/O),
# so this is safe to run at import time.
load_all()
logger.info(
    "modules_loaded",
    count=len(registry),
    names=[m for m in registry.all_metadata()],
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: verify DB �?bootstrap �?yield �?dispose."""
    if not settings.is_test:
        await _verify_db_with_retry()
        await run_bootstrap()

    yield

    if not settings.is_test:
        await dispose_engine()
        logger.info("database_engine_disposed")
    await close_rate_limiter_store()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
    middleware=[
        # Outermost wrapper: records Prometheus metrics for every request.
        StarletteMiddleware(HTTPMetricsMiddleware),
    ],
)


# --- Exception handlers ---


# --- RFC 7807 problem+json ---
# https://datatracker.ietf.org/doc/html/rfc7807
# We emit BOTH the canonical ``application/problem+json`` envelope AND the
# legacy ``detail`` key so existing clients keep working while new clients
# can pivot to the RFC 7807 shape.
_PROBLEM_BASE_URL = "https://docs.scholarhub.example/errors/"


def _problem_response(
    *,
    status: int,
    type_slug: str,
    title: str,
    detail: str,
    instance: str,
    extras: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a problem+json response.

    ``extras`` is merged into the top-level body so we can carry our
    legacy ``errors`` array for validation errors without breaking
    clients that still parse the old shape.
    """
    from app.core.tenant import REQUEST_ID_CTX

    body: dict[str, object] = {
        "type": f"{_PROBLEM_BASE_URL}{type_slug}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
        "trace_id": REQUEST_ID_CTX.get(),
    }
    if extras:
        body.update(extras)
    # Mirror ``detail`` at the legacy key so old clients don't break.
    body.setdefault("detail", detail)
    return JSONResponse(
        status_code=status,
        content=body,
        headers=headers,
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", []))
        errors.append(
            {
                "field": loc,
                "message": err.get("msg", "Invalid value"),
                "type": err.get("type", "value_error"),
            }
        )
    return _problem_response(
        status=422,
        type_slug="validation-error",
        title="Validation error",
        detail="Request body failed schema validation.",
        instance=str(request.url.path),
        extras={"errors": errors},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    headers = getattr(exc, "headers", None)
    extras: dict[str, object] = {}
    # Preserve any structured extras the route attached via ``detail``.
    if isinstance(exc.detail, dict):
        extras = {k: v for k, v in exc.detail.items() if k != "detail"}
        title = str(exc.detail.get("title", "HTTP error"))
        detail_msg = str(exc.detail.get("detail", exc.detail.get("message", "")))
    else:
        title = "HTTP error"
        detail_msg = str(exc.detail)
    return _problem_response(
        status=exc.status_code,
        type_slug=f"http-{exc.status_code}",
        title=title,
        detail=detail_msg,
        instance=str(request.url.path),
        extras=extras,
        headers=headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all unhandled exceptions; never leak stack traces to clients."""
    logger.error(
        "unhandled_exception",
        method=request.method,
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    detail = "Internal server error"
    if settings.debug:
        detail = f"{type(exc).__name__}: {exc}"
    return _problem_response(
        status=500,
        type_slug="internal-server-error",
        title="Internal server error",
        detail=detail,
        instance=str(request.url.path),
    )


# --- Middleware stack (note: FastAPI is LIFO �?last added runs first) ---
#
# Execution order on inbound request (registered here bottom-up):
#   1. TenantContextMiddleware   (resolves tenant, sets request_id)
#   2. RateLimitMiddleware        (per-IP + per-auth-path throttling)
#   3. SecurityHeadersMiddleware (CSP, X-Frame, X-API-Version)
#   4. CSRFMiddleware             (cookie-auth POST/PUT/DELETE only)
#   5. CORSMiddleware
#   6. TrustedHostMiddleware (production only)
# Tenant MUST run before auth, because auth depends on tenant scope.
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware, default_per_minute=settings.rate_limit_per_minute)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

if settings.is_production:
    from fastapi.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

# Tenant must be outermost �?register LAST so it runs first.
app.add_middleware(TenantContextMiddleware)


# --- Core routers (always present) ---
# Health probes at root (Kubernetes convention).
app.include_router(health.router)
app.include_router(health.legacy_router, prefix="/api")
# Prometheus exposition (root, no auth, no rate limit).
app.include_router(metrics_router)
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(gdpr.router, prefix="/api")
app.include_router(privacy.router)
app.include_router(two_factor.router, prefix="/api")
app.include_router(modules.router, prefix="/api")
# OIDC routes always mount; each endpoint 503s when OIDC is not configured
# (default). This avoids a shape change when an operator flips the env flag.
app.include_router(oidc_router, prefix="/api")


# --- Module routers (loaded dynamically at startup) ---
for name, module_router in registry.all_routers():
    app.include_router(module_router, prefix="/api")
    logger.info("module_router_mounted", module=name, prefix=f"/api/{name}")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "ScholarHUB API",
        "version": __version__,
        "docs": "/docs",
    }
