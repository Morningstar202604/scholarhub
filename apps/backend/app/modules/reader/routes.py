"""Reader API routes — reading history + cross-device progress + file assets.

History endpoints (read + write) require authentication; every user sees
only their own history (tenant + user scope enforced by RLS in production
and by the ``tenant_id`` / ``user_id`` filters in tests). FileAsset
endpoints are admin-only: recording stored-file metadata is an
administrative action; the byte upload pipeline itself is a separate
storage-layer concern.

Upsert / retry pattern for ``PUT /progress``:

  1. SELECT the (user, resource) row.
  2. If found, update; if not, INSERT.
  3. On IntegrityError (race: another concurrent INSERT won), rollback
     and re-SELECT, then apply the update to the winner's row.

The semantic where ``duration_sec`` accumulates
across devices — a lost INSERT never loses reading time.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin, require_tenant_id
from app.core.db import get_db, paginate
from app.core.time import utcnow
from app.models import AuditLog, User
from app.modules.catalog.models import Resource
from app.modules.reader.models import FileAsset, ReadingHistory
from app.modules.reader.schemas import (
    FileAssetCreate,
    FileAssetResponse,
    MessageResponse,
    ReadingHistoryEntryResponse,
    ReadingHistoryListResponse,
    ReadingProgressResponse,
    ReadingProgressUpdate,
)

router = APIRouter(prefix="/reader", tags=["reader"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _apply_progress(entry: ReadingHistory, body: ReadingProgressUpdate, now: datetime) -> None:
    """Apply a progress update to an existing entry in place.

    ``duration_sec`` accumulates; the rest overwrite. ``viewed_at`` and
    ``last_read_at`` are bumped so a progress update also counts as a view
    for ordering purposes.
    """
    if body.page is not None:
        entry.page = body.page
    if body.progress_percent is not None:
        entry.progress_percent = body.progress_percent
    if body.duration_sec is not None:
        # Accumulate, never overwrite — multiple devices may report
        # partial durations concurrently.
        entry.duration_sec = (entry.duration_sec or 0) + body.duration_sec
    if body.completed is not None:
        entry.completed = body.completed
    entry.last_read_at = now
    entry.viewed_at = now


# ---------------------------------------------------------------------------
# Reading history
# ---------------------------------------------------------------------------


@router.get("/history", response_model=ReadingHistoryListResponse)
async def list_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReadingHistoryListResponse:
    """List the current user's reading history, newest view first."""
    base = select(ReadingHistory).where(
        ReadingHistory.user_id == current_user.id,
        ReadingHistory.tenant_id == current_user.tenant_id,
    )
    rows, meta = await paginate(
        db,
        base,
        page=page,
        page_size=page_size,
        order_by=(desc(ReadingHistory.viewed_at), ReadingHistory.id.asc()),
    )
    return ReadingHistoryListResponse(
        data=[ReadingHistoryEntryResponse.model_validate(r) for r in rows],
        meta=meta,
    )


@router.post(
    "/history/{resource_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_view(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Record that the current user opened a resource.

    Upserts the (user, resource) row: if it exists, bumps ``visit_count``
    and refreshes ``viewed_at`` / ``last_read_at``; if not, creates it
    with ``visit_count=1``.
    """
    # Reject views for non-existent resources so history cannot point at
    # missing rows. Scope by tenant too — a resource id from another tenant
    # must not be viewable.
    resource = (
        await db.execute(
            select(Resource).where(
                Resource.id == resource_id,
                Resource.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )

    now = utcnow()
    try:
        entry = (
            await db.execute(
                select(ReadingHistory).where(
                    ReadingHistory.user_id == current_user.id,
                    ReadingHistory.resource_id == resource_id,
                    ReadingHistory.tenant_id == current_user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if entry is not None:
            entry.viewed_at = now
            entry.last_read_at = now
            entry.visit_count = (entry.visit_count or 1) + 1
        else:
            entry = ReadingHistory(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                resource_id=resource_id,
                visit_count=1,
                viewed_at=now,
            )
            db.add(entry)
        await db.commit()
    except IntegrityError:
        # Race: another concurrent request inserted the same row. Roll
        # back, re-fetch the winner, and apply the visit bump to it so
        # the upsert still happens.
        await db.rollback()
        entry = (
            await db.execute(
                select(ReadingHistory).where(
                    ReadingHistory.user_id == current_user.id,
                    ReadingHistory.resource_id == resource_id,
                    ReadingHistory.tenant_id == current_user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if entry is not None:
            entry.viewed_at = now
            entry.last_read_at = now
            entry.visit_count = (entry.visit_count or 1) + 1
            await db.commit()
    return MessageResponse(message="Added to history")


@router.delete(
    "/history/{resource_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def remove_from_history(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Remove a resource from the current user's history."""
    entry = (
        await db.execute(
            select(ReadingHistory).where(
                ReadingHistory.user_id == current_user.id,
                ReadingHistory.resource_id == resource_id,
                ReadingHistory.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="History entry not found"
        )
    await db.delete(entry)
    await db.commit()
    return MessageResponse(message="Removed from history")


# ---------------------------------------------------------------------------
# Reading progress
# ---------------------------------------------------------------------------


@router.get(
    "/history/{resource_id}/progress",
    response_model=ReadingProgressResponse,
)
async def get_progress(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReadingProgressResponse:
    """Get the current user's reading progress for a resource."""
    entry = (
        await db.execute(
            select(ReadingHistory).where(
                ReadingHistory.user_id == current_user.id,
                ReadingHistory.resource_id == resource_id,
                ReadingHistory.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Progress not found"
        )
    return ReadingProgressResponse.model_validate(entry)


@router.put(
    "/history/{resource_id}/progress",
    response_model=ReadingProgressResponse,
)
async def update_progress(
    resource_id: int,
    body: ReadingProgressUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReadingProgressResponse:
    """Upsert reading progress for a resource.

    ``duration_sec`` accumulates across calls; the other fields overwrite.
    On a concurrent INSERT race, the loser rolls back, re-fetches the
    winner's row, and re-applies the update so no reading time is lost.
    """
    # Reject progress for non-existent resources so the upsert cannot
    # create an orphaned history row pointing at a missing resource.
    resource = (
        await db.execute(
            select(Resource).where(
                Resource.id == resource_id,
                Resource.tenant_id == current_user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )

    now = utcnow()
    try:
        entry = (
            await db.execute(
                select(ReadingHistory).where(
                    ReadingHistory.user_id == current_user.id,
                    ReadingHistory.resource_id == resource_id,
                    ReadingHistory.tenant_id == current_user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if entry is None:
            entry = ReadingHistory(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                resource_id=resource_id,
                visit_count=1,
                duration_sec=0,
                viewed_at=now,
                last_read_at=now,
            )
            db.add(entry)
        _apply_progress(entry, body, now)
        await db.commit()
        await db.refresh(entry)
    except IntegrityError:
        # Race: another concurrent INSERT won the (user, resource) slot.
        # Re-fetch and re-apply so the update is not lost.
        await db.rollback()
        entry = (
            await db.execute(
                select(ReadingHistory).where(
                    ReadingHistory.user_id == current_user.id,
                    ReadingHistory.resource_id == resource_id,
                    ReadingHistory.tenant_id == current_user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if entry is None:
            # Extremely unlikely: the winner row vanished between the
            # commit and this re-fetch. Surface as 409 so the client retries.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="History entry disappeared after race; please retry",
            ) from None
        _apply_progress(entry, body, now)
        await db.commit()
        await db.refresh(entry)
    return ReadingProgressResponse.model_validate(entry)


# ---------------------------------------------------------------------------
# File assets (admin only)
# ---------------------------------------------------------------------------


@router.get(
    "/file-assets",
    response_model=list[FileAssetResponse],
)
async def list_file_assets(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[FileAssetResponse]:
    """List all file assets in the current tenant (admin only)."""
    tenant_id = require_tenant_id()
    rows = (
        await db.execute(
            select(FileAsset)
            .where(FileAsset.tenant_id == tenant_id)
            .order_by(desc(FileAsset.created_at), FileAsset.id.asc())
        )
    ).scalars().all()
    return [FileAssetResponse.model_validate(r) for r in rows]


@router.get(
    "/file-assets/{file_asset_id}",
    response_model=FileAssetResponse,
)
async def get_file_asset(
    file_asset_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FileAssetResponse:
    """Get a single file asset by id (admin only)."""
    tenant_id = require_tenant_id()
    entry = (
        await db.execute(
            select(FileAsset).where(
                FileAsset.id == file_asset_id,
                FileAsset.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File asset not found"
        )
    return FileAssetResponse.model_validate(entry)


@router.post(
    "/file-assets",
    response_model=FileAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_file_asset(
    payload: FileAssetCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FileAssetResponse:
    """Record metadata for a stored file (admin only).

    The caller must have already written the bytes to the storage
    backend; this endpoint only records what was stored.
    """
    tenant_id = require_tenant_id()
    asset = FileAsset(
        tenant_id=tenant_id,
        filename=payload.filename,
        original_filename=payload.original_filename,
        mime_type=payload.mime_type,
        file_size=payload.file_size,
        storage_path=payload.storage_path,
        storage_backend=payload.storage_backend,
        sha256=payload.sha256,
        uploaded_by=current_user.id,
    )
    db.add(asset)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="File asset with this sha256 already exists in this tenant",
        ) from exc
    await db.refresh(asset)
    # Audit: file-asset metadata is durable evidence (sha256 etc.); log
    # who recorded it so a later dispute can be traced.
    db.add(
        AuditLog(
            tenant_id=current_user.tenant_id,
            actor_user_id=current_user.id,
            action="reader.file_asset.create",
            target_type="file_asset",
            target_id=str(asset.id),
            payload={
                "filename": asset.filename,
                "storage_path": asset.storage_path,
                "sha256": asset.sha256,
            },
        )
    )
    await db.commit()
    return FileAssetResponse.model_validate(asset)


@router.delete(
    "/file-assets/{file_asset_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_file_asset(
    file_asset_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete a file asset record (admin only).

    Does NOT delete the bytes from the storage backend — that is the
    storage layer's responsibility. This endpoint only removes the
    metadata row.
    """
    entry = (
        await db.execute(
            select(FileAsset).where(
                FileAsset.id == file_asset_id,
                FileAsset.tenant_id == require_tenant_id(),
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File asset not found"
        )
    # Capture identifying info before delete so the audit row can describe
    # what was removed (storage_path stays valuable for cleanup audits).
    deleted_filename = entry.filename
    deleted_storage_path = entry.storage_path
    await db.delete(entry)
    db.add(
        AuditLog(
            tenant_id=current_user.tenant_id,
            actor_user_id=current_user.id,
            action="reader.file_asset.delete",
            target_type="file_asset",
            target_id=str(file_asset_id),
            payload={
                "filename": deleted_filename,
                "storage_path": deleted_storage_path,
            },
        )
    )
    await db.commit()
    return MessageResponse(message="File asset deleted")
