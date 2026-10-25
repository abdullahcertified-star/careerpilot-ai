"""Background worker task signatures and queue definitions."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def example_background_task(ctx: dict[str, Any], task_name: str) -> dict[str, str]:
    """Sample background task for worker health and smoke validation."""
    logger.info("Executing background task: %s", task_name)
    return {"status": "completed", "task": task_name}
