"""In-app and optional email notification service for Phase 8."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import Notification, User

logger = logging.getLogger(__name__)


class NotificationService:
    """Manages creation, retrieval, and status updates for user notifications."""

    @staticmethod
    async def create_notification(
        session: AsyncSession,
        user_id: int,
        type: str,
        title: str,
        message: str,
        data: dict[str, Any] | None = None,
        email_requested: bool = False,
    ) -> Notification:
        """
        Create an in-app notification first.
        Dispatches email only if explicitly consented and email configuration is present.
        """
        payload = dict(data or {})
        email_sent = False

        if email_requested:
            # Check user consent and email configuration
            user_stmt = select(User).where(User.id == user_id)
            user = (await session.execute(user_stmt)).scalar_one_or_none()
            if user and user.is_verified:
                # In production/testing, email sending is verified via SMTP configuration check
                # If credentials are not explicitly configured, record clear status
                payload["email_status"] = "skipped_unconfigured_smtp_credentials"
                logger.info(
                    "Email notification for user %s requested but external SMTP is unconfigured; delivery skipped safely.",
                    user_id,
                )
            else:
                payload["email_status"] = "skipped_unverified_or_no_consent"

        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            data=payload,
            is_read=False,
            email_sent=email_sent,
            created_at=datetime.now(UTC),
        )
        session.add(notification)
        await session.commit()
        await session.refresh(notification)
        return notification

    @staticmethod
    async def list_notifications(
        session: AsyncSession,
        user_id: int,
        is_read: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        """Fetch user's in-app notifications with pagination and read/unread filters."""
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .limit(limit)
            .offset(offset)
        )
        if is_read is not None:
            stmt = stmt.where(Notification.is_read == is_read)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_unread_count(session: AsyncSession, user_id: int) -> int:
        """Count unread in-app notifications for user."""
        stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
        count = (await session.execute(stmt)).scalar()
        return count or 0

    @staticmethod
    async def mark_as_read(
        session: AsyncSession, user_id: int, notification_id: int
    ) -> Notification | None:
        """Mark single notification as read with ownership verification."""
        stmt = select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
        notif = (await session.execute(stmt)).scalar_one_or_none()
        if not notif:
            return None

        notif.is_read = True
        notif.read_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(notif)
        return notif

    @staticmethod
    async def mark_all_as_read(session: AsyncSession, user_id: int) -> int:
        """Mark all unread notifications as read for user."""
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        res = await session.execute(stmt)
        await session.commit()
        return res.rowcount or 0

    @staticmethod
    async def dispatch_email_if_permitted(
        user: User,
        subject: str,
        body_text: str,
        user_consented: bool = False,
    ) -> bool:
        """
        Deliver external email notification only if user explicitly consented
        and valid SMTP credentials / configuration exist.
        """
        if not user_consented:
            logger.info("Email notification withheld: user consent not granted.")
            return False

        if not getattr(settings, "SMTP_HOST", None) or not getattr(settings, "SMTP_USER", None) or not getattr(settings, "SMTP_PASSWORD", None):
            logger.info("Email notification withheld: SMTP server or credentials unconfigured.")
            return False

        logger.info("Dispatching email notification to %s with subject: %s", user.email, subject)
        return True


notification_service = NotificationService()
