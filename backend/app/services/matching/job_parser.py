"""Deterministic job description parser extracting structured requirements and qualifications."""

import re
from typing import Dict, List, Optional, Set, Tuple

from app.services.matching.skills_taxonomy import extract_skills_from_text, normalize_skill


class ParsedJobRequirements:
    """Structured representation of extracted job requirements."""

    def __init__(
        self,
        required_skills: Set[str],
        preferred_skills: Set[str],
        responsibilities_text: str,
        required_experience_years: float,
        seniority_level: str,  # intern, entry, mid, senior, staff
        required_education_level: str,  # none, associate, bachelor, master, doctorate
        requires_work_authorization: bool,
        work_mode: str,  # remote, hybrid, onsite, unspecified
        location: Optional[str] = None,
    ) -> None:
        self.required_skills = required_skills
        self.preferred_skills = preferred_skills
        self.responsibilities_text = responsibilities_text
        self.required_experience_years = required_experience_years
        self.seniority_level = seniority_level
        self.required_education_level = required_education_level
        self.requires_work_authorization = requires_work_authorization
        self.work_mode = work_mode
        self.location = location


REQUIRED_SECTION_HEADERS = [
    "basic qualifications",
    "minimum qualifications",
    "minimum requirements",
    "requirements",
    "must have",
    "what you'll need",
    "what you will need",
    "what you need",
    "qualifications",
    "what we're looking for",
    "who you are",
]

PREFERRED_SECTION_HEADERS = [
    "preferred qualifications",
    "preferred skills",
    "preferred experience",
    "nice to have",
    "nice-to-have",
    "bonus points",
    "bonus",
    "plus",
    "desired qualifications",
    "desired skills",
    "what gives you an edge",
    "bonus if you have",
]

RESPONSIBILITIES_SECTION_HEADERS = [
    "responsibilities",
    "what you'll do",
    "what you will do",
    "role overview",
    "key responsibilities",
    "the role",
    "your impact",
    "about the job",
    "what you will be doing",
]


def split_description_into_sections(raw_text: str) -> Dict[str, str]:
    """
    Splits job text into functional sections (required, preferred, responsibilities, general)
    by detecting standard ATS markdown/plain text headings.
    """
    lines = raw_text.splitlines()
    current_section = "general"
    sections: Dict[str, List[str]] = {
        "required": [],
        "preferred": [],
        "responsibilities": [],
        "general": [],
    }

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        clean_header = re.sub(r"^[#*_\-\s]+|[#*_\-:\s]+$", "", stripped).lower()

        # Check section transitions
        matched_section = None
        for pref in PREFERRED_SECTION_HEADERS:
            if clean_header == pref or clean_header.startswith(pref):
                matched_section = "preferred"
                break

        if not matched_section:
            for req in REQUIRED_SECTION_HEADERS:
                if clean_header == req or clean_header.startswith(req):
                    matched_section = "required"
                    break

        if not matched_section:
            for resp in RESPONSIBILITIES_SECTION_HEADERS:
                if clean_header == resp or clean_header.startswith(resp):
                    matched_section = "responsibilities"
                    break

        if matched_section:
            current_section = matched_section
            continue

        sections[current_section].append(stripped)

    return {k: "\n".join(v) for k, v in sections.items()}


def extract_required_experience_years(text: str) -> float:
    """Extracts minimum years of experience required from text using deterministic regex."""
    patterns = [
        r"(?:minimum|at least)\s+(?:of\s+)?(\d+)\+?\s*years?",
        r"(\d+)\s*\+\s*years?(?:\s+of)?\s+(?:relevant\s+)?experience",
        r"(\d+)\s*(?:-|to)\s*(\d+)\s*years?(?:\s+of)?\s+experience",
        r"(\d+)\s*years?(?:\s+of)?\s+(?:professional|industry|software|working)\s+experience",
    ]

    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                continue

    return 0.0


def extract_seniority_level(title: str, text: str, years: float) -> str:
    """Determines target seniority level from title, text, and years."""
    title_lower = title.lower()

    if "intern" in title_lower or "internship" in title_lower:
        return "intern"
    if "junior" in title_lower or "entry" in title_lower or "associate" in title_lower:
        return "entry"
    if "staff" in title_lower or "principal" in title_lower or "distinguished" in title_lower:
        return "staff"
    if "lead" in title_lower or "director" in title_lower or "manager" in title_lower or "vp" in title_lower:
        return "lead"
    if "senior" in title_lower or "sr" in title_lower or years >= 5.0:
        return "senior"
    if years >= 2.0:
        return "mid"
    if years > 0:
        return "entry"

    return "mid"


def extract_education_level(text: str) -> str:
    """Extracts required education level from text."""
    lowered = text.lower()
    if re.search(r"\b(phd|ph\.d|doctorate)\b", lowered):
        return "doctorate"
    if re.search(r"\b(master'?s|ms|m\.s\.|msc)\b", lowered):
        return "master"
    if re.search(r"\b(bachelor'?s|bs|b\.s\.|ba|b\.a\.|undergraduate degree)\b", lowered):
        return "bachelor"
    if re.search(r"\b(associate'?s)\b", lowered):
        return "associate"
    return "none"


def extract_work_authorization_need(text: str) -> bool:
    """Determines if the posting explicitly requires work authorization without sponsorship."""
    lowered = text.lower()
    patterns = [
        r"authorized to work in",
        r"legally authorized",
        r"without sponsorship",
        r"no visa sponsorship",
        r"sponsorship is not available",
        r"must be a u\.?s\.? citizen",
        r"security clearance",
        r"work permit",
        r"right to work",
    ]
    for p in patterns:
        if re.search(p, lowered):
            return True
    return False


def parse_job_requirements(
    title: str,
    description: str,
    location: Optional[str] = None,
    work_mode: str = "unspecified",
) -> ParsedJobRequirements:
    """
    Parses a job posting into structured, categorized requirements
    separating required skills from preferred skills and identifying seniority/education/work-auth rules.
    """
    sections = split_description_into_sections(description)

    req_text = sections["required"]
    pref_text = sections["preferred"]
    resp_text = sections["responsibilities"]
    gen_text = sections["general"]

    # 1. Extract skills per section
    required_skills = extract_skills_from_text(req_text)
    preferred_skills = extract_skills_from_text(pref_text)

    # If no separate required section was found, extract from general and filter out preferred
    if not required_skills and not preferred_skills:
        all_skills = extract_skills_from_text(description)
        # Sentence-level heuristic
        for sentence in re.split(r"[.!?\n]", description):
            s_lower = sentence.lower()
            s_skills = extract_skills_from_text(sentence)
            if not s_skills:
                continue
            if any(w in s_lower for w in ("preferred", "plus", "bonus", "nice to have", "desired")):
                preferred_skills.update(s_skills)
            elif any(w in s_lower for w in ("must", "required", "need", "minimum", "proficiency", "experience in")):
                required_skills.update(s_skills)
            else:
                required_skills.update(s_skills)
    elif not required_skills and preferred_skills:
        # What's in general/responsibilities that isn't preferred is required
        other_skills = extract_skills_from_text(f"{resp_text} {gen_text}")
        required_skills = other_skills - preferred_skills

    # Remove overlaps from preferred
    preferred_skills = preferred_skills - required_skills

    # 2. Extract experience & seniority
    full_text = f"{title}\n{description}"
    years = extract_required_experience_years(f"{req_text}\n{gen_text}\n{full_text}")
    seniority = extract_seniority_level(title, full_text, years)

    # 3. Education
    edu_level = extract_education_level(f"{req_text}\n{gen_text}")

    # 4. Work authorization
    requires_auth = extract_work_authorization_need(full_text)

    # 5. Work mode
    detected_mode = work_mode
    if detected_mode == "unspecified":
        lowered_all = full_text.lower()
        if "remote" in lowered_all or "work from home" in lowered_all:
            detected_mode = "remote"
        elif "hybrid" in lowered_all:
            detected_mode = "hybrid"
        elif location:
            detected_mode = "onsite"

    return ParsedJobRequirements(
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        responsibilities_text=resp_text if resp_text else gen_text,
        required_experience_years=years,
        seniority_level=seniority,
        required_education_level=edu_level,
        requires_work_authorization=requires_auth,
        work_mode=detected_mode,
        location=location,
    )
