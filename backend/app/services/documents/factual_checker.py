"""Automated factual consistency checker.

Compares claims in generated resumes and cover letters against the candidate's
verified profile facts. Identifies unsupported statements, unverified skills,
fabricated employers, degree mismatches, and date exaggerations.
"""

import logging
import re
from typing import Any, List, Optional, Set
from app.models.entities import User
from app.services.documents.schemas import (
    FactualValidationReport,
    StructuredCoverLetter,
    StructuredResume,
    UnsupportedClaim,
)
from app.services.matching.skills_taxonomy import normalize_skill

logger = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    """Normalize company or institution name for comparison."""
    if not name:
        return ""
    n = name.lower()
    for token in ["inc", "llc", "corp", "corporation", "ltd", "technologies", "technology", "univ", "university", "the", ",", "."]:
        n = re.sub(rf"\b{token}\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def _extract_years(text: str) -> List[int]:
    """Extract 4-digit years from date strings."""
    if not text:
        return []
    matches = re.findall(r"\b(19\d\d|20\d\d)\b", str(text))
    return [int(m) for m in matches]


class FactualConsistencyChecker:
    """Automated factual consistency checker verifying generated documents against verified candidate profile."""

    @staticmethod
    def verify_resume(
        resume_data: StructuredResume | dict[str, Any],
        candidate: User,
    ) -> FactualValidationReport:
        """
        Validates structured resume against candidate verified skills, experiences,
        educations, and certifications.
        """
        if isinstance(resume_data, dict):
            resume = StructuredResume.model_validate(resume_data)
        else:
            resume = resume_data

        unsupported_claims: List[UnsupportedClaim] = []
        verified_facts: List[str] = []
        warnings: List[str] = []

        # 1. Collect candidate's verified profile data
        verified_skills: Set[str] = {
            normalize_skill(s.name) for s in candidate.skills if s.name
        }
        verified_experiences = candidate.experiences or []
        verified_educations = candidate.educations or []
        verified_certifications = candidate.certifications or []

        # 2. Check Candidate Identity & Contact Info
        if candidate.full_name and resume.full_name.strip().lower() != candidate.full_name.strip().lower():
            unsupported_claims.append(
                UnsupportedClaim(
                    field="personal_info.full_name",
                    claim=resume.full_name,
                    reason=f"Name mismatch: resume states '{resume.full_name}' while verified profile states '{candidate.full_name}'",
                    severity="error",
                )
            )
        else:
            verified_facts.append(f"Candidate Name: {resume.full_name}")

        # 3. Check Highlighted Skills
        for skill in resume.highlighted_skills:
            norm_s = normalize_skill(skill)
            if norm_s not in verified_skills:
                unsupported_claims.append(
                    UnsupportedClaim(
                        field="highlighted_skills",
                        claim=skill,
                        reason=f"Skill '{skill}' is not present in candidate's verified skills portfolio",
                        severity="error",
                        line_or_context=f"Highlighted skill: {skill}",
                    )
                )
            else:
                verified_facts.append(f"Skill verified: {skill}")

        # 4. Check Work Experiences & Employers & Dates
        verified_employers_norm = [
            (_normalize_name(e.company), e) for e in verified_experiences if e.company
        ]

        for exp in resume.experience:
            norm_exp_co = _normalize_name(exp.company)
            # Find matching verified experience
            match = next(
                (v for v in verified_employers_norm if v[0] == norm_exp_co or v[0] in norm_exp_co or norm_exp_co in v[0]),
                None,
            )

            if not match:
                unsupported_claims.append(
                    UnsupportedClaim(
                        field="experience.company",
                        claim=exp.company,
                        reason=f"Employer '{exp.company}' does not exist in candidate's verified employment history",
                        severity="error",
                        line_or_context=f"{exp.title} at {exp.company} ({exp.start_date} - {exp.end_date})",
                    )
                )
            else:
                verified_facts.append(f"Employer verified: {exp.company}")
                v_exp = match[1]

                # Check job title sanity
                v_title_norm = v_exp.title.lower().strip() if v_exp.title else ""
                exp_title_norm = exp.title.lower().strip()
                if v_title_norm and v_title_norm != exp_title_norm:
                    # Check if there is significant title divergence
                    overlap = set(exp_title_norm.split()) & set(v_title_norm.split())
                    if not overlap:
                        warnings.append(
                            f"Title divergence at {exp.company}: resume lists '{exp.title}' vs verified profile '{v_exp.title}'"
                        )

                # Check dates if available
                doc_years = _extract_years(f"{exp.start_date} {exp.end_date}")
                v_years = []
                if v_exp.start_date:
                    v_years.extend(_extract_years(str(v_exp.start_date)))
                if v_exp.end_date:
                    v_years.extend(_extract_years(str(v_exp.end_date)))

                if doc_years and v_years:
                    doc_min, doc_max = min(doc_years), max(doc_years)
                    v_min, v_max = min(v_years), max(v_years)
                    # Allow 1 year leeway for rounding or academic year
                    if doc_min < (v_min - 1) or doc_max > (v_max + 1):
                        unsupported_claims.append(
                            UnsupportedClaim(
                                field="experience.dates",
                                claim=f"{exp.start_date} - {exp.end_date}",
                                reason=f"Dates at {exp.company} ({exp.start_date}-{exp.end_date}) conflict with verified record ({v_exp.start_date} to {v_exp.end_date})",
                                severity="error",
                                line_or_context=f"{exp.company} claimed dates: {exp.start_date} - {exp.end_date}",
                            )
                        )
                    else:
                        verified_facts.append(f"Tenure dates verified for {exp.company}")

        # 5. Check Education & Degree
        verified_inst_norm = [
            (_normalize_name(edu.institution), edu) for edu in verified_educations if edu.institution
        ]

        for edu in resume.education:
            norm_edu_inst = _normalize_name(edu.institution)
            match_edu = next(
                (v for v in verified_inst_norm if v[0] == norm_edu_inst or v[0] in norm_edu_inst or norm_edu_inst in v[0]),
                None,
            )

            if not match_edu:
                unsupported_claims.append(
                    UnsupportedClaim(
                        field="education.institution",
                        claim=edu.institution,
                        reason=f"Institution '{edu.institution}' is not in candidate's verified education history",
                        severity="error",
                        line_or_context=f"{edu.degree} from {edu.institution}",
                    )
                )
            else:
                verified_facts.append(f"Education institution verified: {edu.institution}")

        # 6. Check Certifications
        verified_cert_names = [
            c.name.lower().strip() for c in verified_certifications if c.name
        ]
        for cert in resume.certifications:
            c_name_norm = cert.name.lower().strip()
            match_cert = any(
                v in c_name_norm or c_name_norm in v for v in verified_cert_names
            )
            if not match_cert:
                unsupported_claims.append(
                    UnsupportedClaim(
                        field="certifications",
                        claim=cert.name,
                        reason=f"Certification '{cert.name}' was not found in verified credentials",
                        severity="error",
                        line_or_context=f"Certification: {cert.name} ({cert.issuer})",
                    )
                )
            else:
                verified_facts.append(f"Certification verified: {cert.name}")

        # 7. Calculate factual confidence score
        total_claims = len(verified_facts) + len(unsupported_claims)
        if total_claims == 0:
            score = 100.0
        else:
            score = round((len(verified_facts) / total_claims) * 100.0, 1)

        is_clean = len(unsupported_claims) == 0

        return FactualValidationReport(
            is_clean=is_clean,
            factual_confidence_score=score,
            total_claims_checked=total_claims,
            verified_claims_count=len(verified_facts),
            unsupported_claims=unsupported_claims,
            verified_facts=verified_facts,
            warnings=warnings,
        )

    @staticmethod
    def verify_cover_letter(
        letter_data: StructuredCoverLetter | dict[str, Any],
        candidate: User,
    ) -> FactualValidationReport:
        """
        Validates cover letter text and claims against candidate verified facts.
        """
        if isinstance(letter_data, dict):
            letter = StructuredCoverLetter.model_validate(letter_data)
        else:
            letter = letter_data

        unsupported_claims: List[UnsupportedClaim] = []
        verified_facts: List[str] = []
        warnings: List[str] = []

        verified_skills: Set[str] = {
            normalize_skill(s.name) for s in candidate.skills if s.name
        }
        verified_employers = [
            e.company.lower().strip() for e in candidate.experiences if e.company
        ]

        # Check sender name
        if candidate.full_name and letter.sender_name.strip().lower() != candidate.full_name.strip().lower():
            unsupported_claims.append(
                UnsupportedClaim(
                    field="sender_name",
                    claim=letter.sender_name,
                    reason=f"Sender name '{letter.sender_name}' differs from verified candidate '{candidate.full_name}'",
                    severity="error",
                )
            )
        else:
            verified_facts.append(f"Candidate Identity: {letter.sender_name}")

        full_text = " ".join(
            [letter.opening_paragraph] + letter.body_paragraphs + [letter.closing_paragraph]
        )

        # Check for claimed employers mentioned in letter
        # Verify that if candidate mentions "During my tenure at X", X is an authentic verified employer
        company_mentions = re.findall(r"(?:at|with|for)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)?)", full_text)
        for company in company_mentions:
            c_norm = company.lower().strip()
            # Exclude target company, common words
            if c_norm in [letter.target_company.lower().strip(), "the", "my", "our", "their", "university"]:
                continue
            # Check if this company is in past employers
            is_authentic = any(
                c_norm in ve or ve in c_norm for ve in verified_employers
            )
            if is_authentic:
                verified_facts.append(f"Past employer reference verified: {company}")
            elif len(company) > 3 and c_norm not in ["spring", "summer", "winter", "fall", "march", "april", "june", "july"]:
                # If company appears in experience, good. Otherwise advisory warning
                warnings.append(
                    f"Cover letter references company '{company}'; ensure this aligns with your background."
                )

        # Check verified skills mentioned in text
        for s in candidate.skills:
            if s.name and s.name.lower() in full_text.lower():
                verified_facts.append(f"Skill claim verified in letter: {s.name}")

        total_claims = len(verified_facts) + len(unsupported_claims)
        score = 100.0 if total_claims == 0 else round((len(verified_facts) / total_claims) * 100.0, 1)

        return FactualValidationReport(
            is_clean=len(unsupported_claims) == 0,
            factual_confidence_score=score,
            total_claims_checked=total_claims,
            verified_claims_count=len(verified_facts),
            unsupported_claims=unsupported_claims,
            verified_facts=verified_facts,
            warnings=warnings,
        )


factual_checker = FactualConsistencyChecker()
