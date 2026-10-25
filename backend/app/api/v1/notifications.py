"""API endpoints for Phase 8 in-app notifications."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import User
from app.services.scheduler.notification_service import notification_service
from app.services.scheduler.schemas import (
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)

router = APIRouter(prefix="/notifications", tags=["In-App Notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List candidate notifications",
)
async def list_notifications(
    is_read: bool | None = Query(default=None, description="Filter by read status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve in-app notifications with pagination and unread counts."""
    notifications = await notification_service.list_notifications(
        session=db,
        user_id=current_user.id,
        is_read=is_read,
        limit=limit,
        offset=offset,
    )
    unread_count = await notification_service.get_unread_count(
        session=db, user_id=current_user.id
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total_count=len(notifications),
        unread_count=unread_count,
    )


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCountResponse,
    summary="Get unread notification count badge",
)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the quick count of unread notifications for navigation badges."""
    count = await notification_service.get_unread_count(
        session=db, user_id=current_user.id
    )
    return NotificationUnreadCountResponse(unread_count=count)


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark notification as read",
)
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark single notification as read with ownership verification."""
    notif = await notification_service.mark_as_read(
        session=db, user_id=current_user.id, notification_id=notification_id
    )
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found"
        )
    return NotificationResponse.model_validate(notif)


@router.post(
    "/read-all",
    summary="Mark all notifications as read",
)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread notifications as read for current user."""
    updated_count = await notification_service.mark_all_as_read(
        session=db, user_id=current_user.id
    )
    return {"marked_as_read_count": updated_count, "status": "success"}
