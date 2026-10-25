from datetime import datetime, timezone
from typing import Optional
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_session_token
from app.models.entities import User, UserSession


async def get_session_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    cookie_token: Optional[str] = Cookie(None, alias=settings.SESSION_COOKIE_NAME),
) -> str:
    """Extract session token from Bearer Authorization header or HTTP-only cookie."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token

    if cookie_token and cookie_token.strip():
        return cookie_token.strip()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: str = Depends(get_session_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate server-managed session and resolve current authenticated user."""
    token_hash = hash_session_token(token)
    now = datetime.now(timezone.utc)

    # Query active session
    stmt = (
        select(UserSession)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.is_revoked.is_(False),
            UserSession.expires_at > now,
        )
        .options(selectinload(UserSession.user))
    )
    result = await db.execute(stmt)
    session_obj = result.scalar_one_or_none()

    if not session_obj or not session_obj.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = session_obj.user
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


async def get_optional_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    cookie_token: Optional[str] = Cookie(None, alias=settings.SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Resolves current user if authenticated, returns None otherwise."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif cookie_token and cookie_token.strip():
        token = cookie_token.strip()

    if not token:
        return None

    try:
        token_hash = hash_session_token(token)
        now = datetime.now(timezone.utc)
        stmt = (
            select(UserSession)
            .where(
                UserSession.token_hash == token_hash,
                UserSession.is_revoked.is_(False),
                UserSession.expires_at > now,
            )
            .options(selectinload(UserSession.user))
        )
        result = await db.execute(stmt)
        session_obj = result.scalar_one_or_none()
        if session_obj and session_obj.user and session_obj.user.is_active:
            return session_obj.user
    except Exception:
        pass
    return None

