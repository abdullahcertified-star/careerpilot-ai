from collections.abc import AsyncGenerator
import logging
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    pass


def normalize_database_url(url: str) -> str:
    """Normalize database URL for async drivers (SQLite, PostgreSQL, or Neon)."""
    import re
    if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # asyncpg does not support channel_binding or sslmode parameters passed directly in query
    if "asyncpg" in url:
        url = re.sub(r"[?&]channel_binding=[^&]+", "", url)
        url = url.replace("sslmode=", "ssl=")
        # Fix query string if channel_binding was first param: url?&ssl=require -> url?ssl=require
        url = url.replace("?&", "?")
        url = url.rstrip("?&")
    return url


# Normalize database URL
db_url = normalize_database_url(settings.DATABASE_URL)

engine_kwargs: dict[str, Any] = {"echo": False, "future": True}
if "sqlite" in db_url:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True

engine: AsyncEngine = create_async_engine(db_url, **engine_kwargs)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields a database session and safely closes it."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health() -> dict[str, str | bool]:
    """Ping database and report status."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"connected": True, "driver": engine.dialect.name}
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        return {"connected": False, "error": "Database connection unavailable"}
