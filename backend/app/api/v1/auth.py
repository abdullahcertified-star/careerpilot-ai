from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session_token
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit_auth
from app.core.security import generate_session_token, hash_password, hash_session_token, verify_password
from app.models.entities import Profile, User, UserSession
from app.schemas.auth import (
    AuthResponse,
    MessageResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def set_session_cookie(response: Response, token: str, max_age: int) -> None:
    """Set secure HTTP-only cookie for session management."""
    is_prod = settings.APP_ENV.lower() == "production"
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        expires=max_age,
        path="/",
        httponly=True,
        secure=is_prod,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    """Clear session cookie upon logout."""
    is_prod = settings.APP_ENV.lower() == "production"
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=is_prod,
        samesite="lax",
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth)],
)
async def register(
    payload: UserRegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Register a new candidate account with unique email verification."""
    # Check if email is already taken
    stmt = select(User).where(User.email == payload.email.lower().strip())
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    # Create user
    hashed = hash_password(payload.password)
    new_user = User(
        email=payload.email.lower().strip(),
        hashed_password=hashed,
        full_name=payload.full_name.strip(),
        role="candidate",
        is_active=True,
        is_verified=False,
    )
    db.add(new_user)
    await db.flush()

    # Automatically create default empty profile
    default_profile = Profile(
        user_id=new_user.id,
        target_job_titles=[],
        remote_preference="flexible",
    )
    db.add(default_profile)

    # Create server-managed session
    token, token_hash = generate_session_token()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:255]

    session_record = UserSession(
        user_id=new_user.id,
        token_hash=token_hash,
        ip_address=client_ip,
        user_agent=user_agent,
        expires_at=expires_at,
        is_revoked=False,
    )
    db.add(session_record)
    await db.commit()
    await db.refresh(new_user)

    set_session_cookie(response, token, settings.SESSION_MAX_AGE_SECONDS)

    return AuthResponse(
        user=UserResponse.model_validate(new_user),
        token=token,
        expires_at=expires_at,
        message="Account created successfully",
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(rate_limit_auth)],
)
async def login(
    payload: UserLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate with email and password, creating a server-managed session."""
    stmt = select(User).where(User.email == payload.email.lower().strip())
    user = (await db.execute(stmt)).scalar_one_or_none()

    # Safe comparison to prevent timing attacks
    valid_password = False
    if user:
        valid_password = verify_password(payload.password, user.hashed_password)

    if not user or not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact support.",
        )

    token, token_hash = generate_session_token()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:255]

    session_record = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        ip_address=client_ip,
        user_agent=user_agent,
        expires_at=expires_at,
        is_revoked=False,
    )
    db.add(session_record)
    await db.commit()

    set_session_cookie(response, token, settings.SESSION_MAX_AGE_SECONDS)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        token=token,
        expires_at=expires_at,
        message="Login successful",
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    token: str = Depends(get_session_token),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Invalidate current session token in database and clear browser cookie."""
    token_hash = hash_session_token(token)
    stmt = select(UserSession).where(UserSession.token_hash == token_hash)
    session_record = (await db.execute(stmt)).scalar_one_or_none()

    if session_record:
        session_record.is_revoked = True
        await db.commit()

    clear_session_cookie(response)
    return MessageResponse(message="Successfully logged out.")


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Retrieve currently authenticated user details."""
    return UserResponse.model_validate(current_user)
