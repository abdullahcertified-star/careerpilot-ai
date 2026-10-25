"""API endpoints for Phase 8 user-configured saved searches and scheduled scans."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import User
from app.services.scheduler.redis_client import RedisUnavailableError
from app.services.scheduler.schemas import (
    SavedSearchCreate,
    SavedSearchListResponse,
    SavedSearchResponse,
    SavedSearchUpdate,
    ScanCancelResponse,
    ScheduledScanRunResponse,
)
from app.services.scheduler.service import saved_search_service

router = APIRouter(
    prefix="/saved-searches", tags=["Saved Searches & Scheduled Discovery"]
)


@router.post(
    "",
    response_model=SavedSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new saved search",
)
async def create_saved_search(
    payload: SavedSearchCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create user-configured saved search and schedule initial background scan."""
    try:
        search = await saved_search_service.create_saved_search(
            session=db, user_id=current_user.id, payload=payload
        )
        return saved_search_service.to_response(search)
    except RedisUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "",
    response_model=SavedSearchListResponse,
    summary="List candidate's saved searches",
)
async def list_saved_searches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all saved searches configured by the authenticated candidate."""
    searches = await saved_search_service.list_saved_searches(
        session=db, user_id=current_user.id
    )
    items = [saved_search_service.to_response(s) for s in searches]
    active_count = sum(1 for s in searches if s.is_active)
    paused_count = len(searches) - active_count
    return SavedSearchListResponse(
        items=items,
        total_count=len(items),
        active_count=active_count,
        paused_count=paused_count,
    )


@router.get(
    "/{search_id}",
    response_model=SavedSearchResponse,
    summary="Get saved search details and metrics",
)
async def get_saved_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve detailed configuration and latest scan metrics for a saved search."""
    search = await saved_search_service.get_saved_search(
        session=db, user_id=current_user.id, search_id=search_id
    )
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found"
        )
    return saved_search_service.to_response(search)


@router.put(
    "/{search_id}",
    response_model=SavedSearchResponse,
    summary="Update saved search configuration",
)
async def update_saved_search(
    search_id: int,
    payload: SavedSearchUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Edit criteria, interval, score thresholds, or notification preferences."""
    search = await saved_search_service.update_saved_search(
        session=db, user_id=current_user.id, search_id=search_id, payload=payload
    )
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found"
        )
    return saved_search_service.to_response(search)


@router.delete(
    "/{search_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a saved search",
)
async def delete_saved_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete saved search and remove any future scheduled scans."""
    deleted = await saved_search_service.delete_saved_search(
        session=db, user_id=current_user.id, search_id=search_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found"
        )
    return None


@router.post(
    "/{search_id}/pause",
    response_model=SavedSearchResponse,
    summary="Pause scheduled scanning for search",
)
async def pause_saved_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause automatic background scanning for this saved search."""
    search = await saved_search_service.pause_saved_search(
        session=db, user_id=current_user.id, search_id=search_id
    )
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found"
        )
    return saved_search_service.to_response(search)


@router.post(
    "/{search_id}/resume",
    response_model=SavedSearchResponse,
    summary="Resume scheduled scanning for search",
)
async def resume_saved_search(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume automatic background scanning and schedule next scan."""
    search = await saved_search_service.resume_saved_search(
        session=db, user_id=current_user.id, search_id=search_id
    )
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found"
        )
    return saved_search_service.to_response(search)


@router.post(
    "/{search_id}/run-now",
    response_model=ScheduledScanRunResponse,
    summary="Trigger immediate scan execution",
)
async def trigger_run_now(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an on-demand immediate execution of this saved search."""
    try:
        run = await saved_search_service.trigger_immediate_scan(
            session=db, user_id=current_user.id, search_id=search_id
        )
        return ScheduledScanRunResponse.model_validate(run)
    except RedisUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/{search_id}/cancel",
    response_model=ScanCancelResponse,
    summary="Cancel active scan execution",
)
async def cancel_scan(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Request immediate cancellation of an in-progress scan."""
    try:
        await saved_search_service.cancel_running_scan(
            session=db, user_id=current_user.id, search_id=search_id
        )
        return ScanCancelResponse(
            saved_search_id=search_id,
            status="cancellation_requested",
            message="Cancellation signal dispatched to background worker",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/{search_id}/runs",
    response_model=list[ScheduledScanRunResponse],
    summary="List scan execution history for a saved search",
)
async def get_scan_runs(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduledScanRunResponse]:
    """Inspect execution history, duration, and error logs for a saved search."""
    try:
        runs = await saved_search_service.get_scan_runs(
            session=db, user_id=current_user.id, search_id=search_id
        )
        return [ScheduledScanRunResponse.model_validate(r) for r in runs]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
