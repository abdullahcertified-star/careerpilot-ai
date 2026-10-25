"""Matching and scoring engine package."""

from app.services.matching.engine import (
    DEFAULT_MATCHING_WEIGHTS,
    DeterministicMatchingEngine,
    MatchBreakdown,
    SCORING_VERSION,
    matching_engine,
)
from app.services.matching.job_parser import (
    ParsedJobRequirements,
    parse_job_requirements,
)
from app.services.matching.skills_taxonomy import (
    SKILL_SYNONYMS,
    extract_skills_from_text,
    normalize_skill,
)

__all__ = [
    "DeterministicMatchingEngine",
    "matching_engine",
    "DEFAULT_MATCHING_WEIGHTS",
    "MatchBreakdown",
    "SCORING_VERSION",
    "parse_job_requirements",
    "ParsedJobRequirements",
    "normalize_skill",
    "extract_skills_from_text",
    "SKILL_SYNONYMS",
]
