"""Sensitive data redaction and safe LangSmith tracing integration for Phase 6."""

import logging
import re
from typing import Any, Dict, List, Optional, Set
from langchain_core.tracers.base import BaseTracer
from langchain_core.tracers.schemas import Run

logger = logging.getLogger(__name__)

# Keys whose values should always be masked
SENSITIVE_KEY_PATTERNS = {
    re.compile(r".*(token|secret|password|api[_-]?key|auth|bearer|cookie).*", re.IGNORECASE),
    re.compile(r".*(cv[_-]?text|raw[_-]?cv|parsed[_-]?text|resume[_-]?text).*", re.IGNORECASE),
    re.compile(r".*(ssn|social[_-]?security|passport|credit[_-]?card).*", re.IGNORECASE),
}

# Substring values pattern (e.g. bearer tokens or jwt)
JWT_PATTERN = re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}")
OPENAI_KEY_PATTERN = re.compile(r"sk-[a-zA-Z0-9T3BlbkFJ]{20,}")


def is_sensitive_key(key: str) -> bool:
    """Check if dictionary key matches sensitive patterns."""
    return any(p.match(key) for p in SENSITIVE_KEY_PATTERNS)


def redact_sensitive_value(value: Any, key_name: str = "") -> Any:
    """Recursively mask sensitive values, tokens, and raw CV content."""
    if value is None:
        return None

    if is_sensitive_key(key_name):
        return "[REDACTED_CONFIDENTIAL]"

    if isinstance(value, str):
        # Mask JWT tokens
        sanitized = JWT_PATTERN.sub("[REDACTED_JWT_TOKEN]", value)
        # Mask API keys
        sanitized = OPENAI_KEY_PATTERN.sub("[REDACTED_API_KEY]", sanitized)
        # If string is massive raw text containing candidate personal info
        if len(sanitized) > 5000 and any(kw in sanitized.lower() for kw in ["curriculum vitae", "resume", "confidential"]):
            return f"[REDACTED_RAW_DOCUMENT_BODY: {len(sanitized)} chars]"
        return sanitized

    if isinstance(value, dict):
        redacted_dict: Dict[str, Any] = {}
        for k, v in value.items():
            if is_sensitive_key(k):
                redacted_dict[k] = "[REDACTED_CONFIDENTIAL]"
            else:
                redacted_dict[k] = redact_sensitive_value(v, str(k))
        return redacted_dict

    if isinstance(value, (list, tuple, set)):
        redacted_list = [redact_sensitive_value(item, key_name) for item in value]
        return type(value)(redacted_list) if not isinstance(value, (set, tuple)) else list(redacted_list)

    return value


class RedactingLangSmithTracer(BaseTracer):
    """LangSmith tracer with automated sensitive data redaction and failure isolation."""

    def __init__(self, run_tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.run_tags = run_tags or ["careerpilot", "phase-6-workflow"]
        self.metadata = metadata or {}

    def _persist_run(self, run: Run) -> None:
        """Sanitize run inputs and outputs before persisting, with failure isolation."""
        try:
            if run.inputs:
                run.inputs = redact_sensitive_value(run.inputs)
            if run.outputs:
                run.outputs = redact_sensitive_value(run.outputs)
            if run.extra and "metadata" in run.extra:
                run.extra["metadata"] = redact_sensitive_value(run.extra["metadata"])
        except Exception as e:
            # LangSmith redaction or tracing failures must NEVER crash core workflows
            logger.warning("Tracer redaction handled exception gracefully: %s", e)
