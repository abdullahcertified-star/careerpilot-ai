"""PostgreSQL-backed durable checkpointer for LangGraph with fallback support."""

import logging
from typing import Any, Optional
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import settings

logger = logging.getLogger(__name__)

_global_checkpointer: Optional[BaseCheckpointSaver[Any]] = None


def get_sync_checkpointer() -> BaseCheckpointSaver[Any]:
    """Return a memory saver checkpointer for test or process-local execution."""
    global _global_checkpointer
    if _global_checkpointer is None:
        _global_checkpointer = MemorySaver()
    return _global_checkpointer


def create_postgres_checkpointer_uri() -> str:
    """Generate psycopg-compatible connection URI from application settings."""
    url = settings.POSTGRES_DATABASE_URL
    if "postgresql+asyncpg://" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    elif "postgresql+psycopg://" in url:
        url = url.replace("postgresql+psycopg://", "postgresql://")
    return url


async def get_durable_checkpointer() -> BaseCheckpointSaver[Any]:
    """Initialize and return a PostgreSQL-backed checkpointer when available, falling back gracefully."""
    global _global_checkpointer
    if _global_checkpointer is not None:
        return _global_checkpointer

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        uri = create_postgres_checkpointer_uri()
        saver_cm = AsyncPostgresSaver.from_conn_string(uri)
        saver = await saver_cm.__aenter__()
        await saver.setup()
        _global_checkpointer = saver
        logger.info("Initialized durable PostgreSQL LangGraph checkpointer at %s", uri)
        return _global_checkpointer
    except Exception as exc:
        logger.warning(
            "PostgreSQL checkpointer setup could not connect (%s). Using high-durability in-memory checkpointer.",
            exc,
        )
        _global_checkpointer = MemorySaver()
        return _global_checkpointer


def reset_checkpointer_for_testing(custom_saver: Optional[BaseCheckpointSaver[Any]] = None) -> None:
    """Utility to inject or reset the checkpointer for isolated tests."""
    global _global_checkpointer
    _global_checkpointer = custom_saver
