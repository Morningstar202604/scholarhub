"""Health endpoints: liveness, readiness."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.db import get_db
from app.schemas import HealthReadyResponse, HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Liveness probe — always 200 if the process is alive."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/ready", response_model=HealthReadyResponse)
async def readiness(
    db: AsyncSession = Depends(get_db),
) -> HealthReadyResponse | JSONResponse:
    """Readiness probe — verifies DB reachability. Returns 503 on failure."""
    try:
        await db.execute(text("SELECT 1"))
        return HealthReadyResponse(status="ok", database="connected")
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "database": "unavailable"},
        )
