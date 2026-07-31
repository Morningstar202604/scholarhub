"""Export API routes — ``GET /api/export`` downloads a citation file.

Public endpoint (no auth required, like the catalog list). The caller
supplies ``ids`` (repeated query param) and ``format``; the endpoint
fetches matching resources from the catalog module and pipes them
through the serializer.

Cap on ids is enforced to bound response size and DB load.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_tenant_id
from app.core.db import get_db
from app.modules.catalog.models import Resource
from app.modules.export.exporters import (
    FILE_EXTENSIONS,
    MIME_TYPES,
    Exportable,
    export_resources,
)

router = APIRouter(prefix="/export", tags=["export"])

EXPORT_MAX_IDS = 500


@router.get("", response_class=Response)
async def export_endpoint(
    ids: list[int] = Query(default_factory=list),
    format: str = Query(default="json", pattern=r"^(bibtex|ris|csv|json)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download the given resources as a BibTeX / RIS / CSV / JSON file.

    Public (no auth). ``ids`` is a repeated query param
    (``?ids=1&ids=2``); up to ``EXPORT_MAX_IDS`` are honoured. Unknown ids
    are silently dropped; if none resolve, a 404 is returned. The query
    is scoped by tenant — exporting a resource from another tenant is
    treated the same as a non-existent id (silently dropped).
    """
    requested_ids = list(ids)
    if len(requested_ids) > EXPORT_MAX_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many ids requested ({len(requested_ids)}); limit is {EXPORT_MAX_IDS}.",
        )
    if not requested_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one `ids` query parameter is required.",
        )

    tenant_id = require_tenant_id()
    result = await db.execute(
        select(Resource).where(
            Resource.id.in_(requested_ids),
            Resource.tenant_id == tenant_id,
        )
    )
    resources_by_id = {r.id: r for r in result.scalars().all()}

    # Preserve caller's requested order and drop missing ids.
    ordered = [resources_by_id[i] for i in requested_ids if i in resources_by_id]
    if not ordered:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No resources found for the given ids.",
        )

    try:
        # Resource satisfies Exportable structurally (duck-typed), but
        # mypy can't see that without a runtime check; cast through.
        body = export_resources(format, cast(list[Exportable], ordered))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    extension = FILE_EXTENSIONS[format]
    media_type = MIME_TYPES[format]
    filename = f"scholarhub-export.{extension}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
