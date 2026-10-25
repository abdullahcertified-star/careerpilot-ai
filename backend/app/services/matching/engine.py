"""Deterministic, explainable job matching and ranking engine."""

from dataclasses import dataclass, field
from datetime import date, datetime
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.entities import Certification, Education, Experience, JobPosting, Profile, Skill, User
from app.services.matching.job_parser import ParsedJobRequirements, parse_job_requirements
from app.services.matching.skills_taxonomy import normalize_skill

SCORING_VERSION = "1.0.0"

# Initial Configurable Weights (Must sum exactly to 1.0 / 100%)
DEFAULT_MATCHING_WEIGHTS: Dict[str, float] = {
    "required_skills": 0.35,
    "role_relevance": 0.25,
    "experience_seniority": 0.15,
    "education_certifications": 0.10,
    "location_work_authorization": 0.10,
    "preferred_skills": 0.05,
}


@dataclass
class MatchBreakdown:
    """Full explainable breakdown of a candidate-job match evaluation."""

    total_score: float
    component_scores: Dict[str, float]
    weights_used: Dict[str, float]
    matched_skills: List[Dict[str, Any]]
    missing_skills: List[str]
    missing_preferred_skills: List[str]
    candidate_facts_state: Dict[str, str]  # verified, unverified, conflicting, unknown
    explanation: str
    scoring_version: str = SCORING_VERSION
    candidate_profile_version: int = 1


class DeterministicMatchingEngine:
    """
    Deterministic job scoring and candidate alignment engine.
    Calculates transparent, reproducible compatibility scores without LLM hallucinations.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None) -> None:
        self.weights = weights or DEFAULT_MATCHING_WEIGHTS.copy()
        # Ensure weights sum to 1.0 (with floating point tolerance)
        total_w = sum(self.weights.values())
        if not math.isclose(total_w, 1.0, rel_tol=1e-5):
            raise ValueError(f"Matching weights must sum to 1.0 (100%), got {total_w:.4f}")

    def score_required_skills(
        self, candidate_skills: Dict[str, Skill], required_skills: Set[str]
    ) -> Tuple[float, List[Dict[str, Any]], List[str]]:
        """
        Scores required skills component (0-100).
        Missing required skills reduce the score directly.
        """
        if not required_skills:
            return 100.0, [], []

        matched: List[Dict[str, Any]] = []
        missing: List[str] = []
        earned_points = 0.0

        for req in sorted(required_skills):
            norm_req = normalize_skill(req)
            candidate_skill = candidate_skills.get(norm_req)

            if candidate_skill:
                prof = candidate_skill.proficiency_level.lower()
                # Weight by proficiency
                if prof in ("expert", "advanced"):
                    mult = 1.0
                elif prof == "intermediate":
                    mult = 0.85
                else:  # beginner / elementary
                    mult = 0.65

                earned_points += mult
                matched.append({
                    "skill": norm_req,
                    "proficiency": candidate_skill.proficiency_level,
                    "years": candidate_skill.years_experience,
                    "verified": True,
                })
            else:
                missing.append(norm_req)

        score = (earned_points / len(required_skills)) * 100.0
        return min(max(score, 0.0), 100.0), matched, missing

    def score_preferred_skills(
        self, candidate_skills: Dict[str, Skill], preferred_skills: Set[str]
    ) -> Tuple[float, List[Dict[str, Any]], List[str]]:
        """Scores preferred/bonus skills component (0-100)."""
        if not preferred_skills:
            return 100.0, [], []

        matched: List[Dict[str, Any]] = []
        missing: List[str] = []
        earned_points = 0.0

        for pref in sorted(preferred_skills):
            norm_pref = normalize_skill(pref)
            if norm_pref in candidate_skills:
                skill_obj = candidate_skills[norm_pref]
                earned_points += 1.0
                matched.append({
                    "skill": norm_pref,
                    "proficiency": skill_obj.proficiency_level,
                    "years": skill_obj.years_experience,
                    "is_preferred": True,
                })
            else:
                missing.append(norm_pref)

        score = (earned_points / len(preferred_skills)) * 100.0
        return min(max(score, 0.0), 100.0), matched, missing

    def score_role_relevance(
        self,
        job_title: str,
        responsibilities_text: str,
        target_job_titles: List[str],
        experiences: List[Experience],
    ) -> float:
        """Scores alignment between job role and candidate target roles / experience."""
        job_tokens = set(re.findall(r"\b\w{3,}\b", job_title.lower()))
        score = 40.0  # Baseline

        # Check candidate target job titles
        target_match = False
        for target in target_job_titles:
            target_tokens = set(re.findall(r"\b\w{3,}\b", target.lower()))
            overlap = job_tokens.intersection(target_tokens)
            if overlap:
                overlap_ratio = len(overlap) / max(len(job_tokens), 1)
                score += overlap_ratio * 35.0
                target_match = True
                break

        # Check past job titles in candidate experience
        exp_match = False
        for exp in experiences:
            exp_tokens = set(re.findall(r"\b\w{3,}\b", exp.title.lower()))
            overlap = job_tokens.intersection(exp_tokens)
            if overlap:
                overlap_ratio = len(overlap) / max(len(job_tokens), 1)
                score += overlap_ratio * 25.0
                exp_match = True
                break

        if not target_match and not exp_match:
            # Check domain similarity in responsibilities text
            resp_tokens = set(re.findall(r"\b\w{4,}\b", responsibilities_text.lower()))
            candidate_domain_tokens = set()
            for exp in experiences:
                if exp.description:
                    candidate_domain_tokens.update(re.findall(r"\b\w{4,}\b", exp.description.lower()))
            domain_overlap = resp_tokens.intersection(candidate_domain_tokens)
            if domain_overlap:
                score += min(len(domain_overlap) * 1.5, 20.0)

        return min(max(score, 0.0), 100.0)

    def score_experience_seniority(
        self,
        candidate_years: float,
        required_years: float,
        target_seniority: str,
        experiences: List[Experience],
    ) -> float:
        """Scores candidate years of experience and seniority level alignment."""
        # 1. Seniority alignment
        if target_seniority == "intern":
            # For internships, candidates with 0-1 years get highest score
            if candidate_years <= 1.5:
                return 100.0
            elif candidate_years <= 3.0:
                return 80.0
            else:
                return 65.0  # overqualified

        if target_seniority == "entry":
            if candidate_years <= 2.0:
                return 100.0
            elif candidate_years <= 4.0:
                return 90.0
            else:
                return 80.0

        if target_seniority == "senior":
            if candidate_years >= 5.0:
                base = 100.0
            elif candidate_years >= 3.0:
                base = 70.0
            elif candidate_years >= 1.0:
                base = 35.0
            else:
                base = 10.0
            return base

        if target_seniority == "staff" or target_seniority == "lead":
            if candidate_years >= 8.0:
                return 100.0
            elif candidate_years >= 5.0:
                return 75.0
            elif candidate_years >= 3.0:
                return 40.0
            else:
                return 15.0

        # Mid level default
        if required_years > 0:
            if candidate_years >= required_years:
                return 100.0
            else:
                ratio = candidate_years / required_years
                return max(ratio * 100.0, 20.0)

        # Neutral fallback
        return 80.0 if candidate_years >= 2.0 else 60.0

    def score_education_certifications(
        self,
        educations: List[Education],
        certifications: List[Certification],
        required_edu_level: str,
        candidate_years: float,
    ) -> float:
        """Scores degree level compliance and professional certifications."""
        degree_ranks = {"none": 0, "associate": 1, "bachelor": 2, "master": 3, "doctorate": 4}
        req_rank = degree_ranks.get(required_edu_level, 0)

        cand_max_rank = 0
        for edu in educations:
            deg = edu.degree.lower()
            if "phd" in deg or "doctor" in deg:
                cand_max_rank = max(cand_max_rank, 4)
            elif "master" in deg or "ms" in deg or "msc" in deg:
                cand_max_rank = max(cand_max_rank, 3)
            elif "bachelor" in deg or "bs" in deg or "ba" in deg:
                cand_max_rank = max(cand_max_rank, 2)
            elif "associate" in deg:
                cand_max_rank = max(cand_max_rank, 1)

        # Baseline degree score
        if req_rank == 0:
            edu_score = 90.0 if cand_max_rank > 0 else 80.0
        elif cand_max_rank >= req_rank:
            edu_score = 100.0
        elif cand_max_rank == req_rank - 1:
            # 1 level below (e.g. Bachelor's when Master's requested)
            # Experience can compensate
            edu_score = 80.0 if candidate_years >= 3.0 else 65.0
        else:
            # Missing degree completely
            edu_score = 50.0 if candidate_years >= 4.0 else 25.0

        # Certifications bonus (+5 per certification up to +15 max)
        cert_bonus = min(len(certifications) * 5.0, 15.0)
        return min(edu_score + cert_bonus, 100.0)

    def score_location_and_work_auth(
        self,
        job_work_mode: str,
        job_location: Optional[str],
        requires_work_auth: bool,
        candidate_remote_pref: str,
        candidate_location: Optional[str],
        candidate_work_auth_status: Optional[str],
    ) -> Tuple[float, Dict[str, str], List[str]]:
        """
        Scores location and work authorization alignment.
        CRITICAL RULE: Unknown work authorization is NOT assumed to be eligible!
        """
        loc_score = 0.0
        notes: List[str] = []
        fact_states: Dict[str, str] = {}

        # 1. Work Mode Compatibility (50 points max)
        job_mode = job_work_mode.lower()
        cand_pref = (candidate_remote_pref or "flexible").lower()

        if job_mode == "remote":
            if cand_pref in ("remote", "flexible", "hybrid"):
                loc_score += 50.0
                fact_states["work_mode"] = "verified"
            else:
                loc_score += 30.0
                fact_states["work_mode"] = "partial"
        elif job_mode == "hybrid":
            if cand_pref in ("hybrid", "flexible"):
                loc_score += 50.0
                fact_states["work_mode"] = "verified"
            elif cand_pref == "remote":
                loc_score += 20.0
                fact_states["work_mode"] = "conflicting"
                notes.append("Job is hybrid but candidate prefers fully remote.")
            else:
                loc_score += 40.0
        else:  # Onsite
            # Check location proximity
            if candidate_location and job_location:
                cand_loc_clean = candidate_location.lower()
                job_loc_clean = job_location.lower()
                if any(part in job_loc_clean for part in cand_loc_clean.split(",")):
                    loc_score += 50.0
                    fact_states["location"] = "verified"
                elif cand_pref == "remote":
                    loc_score += 10.0
                    fact_states["location"] = "conflicting"
                    notes.append(f"Job is onsite in '{job_location}', but candidate prefers remote.")
                else:
                    loc_score += 30.0
                    fact_states["location"] = "unverified"
            elif cand_pref == "remote":
                loc_score += 15.0
                fact_states["location"] = "conflicting"
            else:
                loc_score += 40.0

        # 2. Work Authorization Evaluation (50 points max)
        # CRITICAL: Do not treat missing information as proof that candidate meets requirement!
        auth_status = (candidate_work_auth_status or "").lower().strip()

        if requires_work_auth:
            if not auth_status or auth_status == "unknown":
                # Unknown work authorization is NOT assumed to be eligible
                loc_score += 15.0  # Reduced significantly
                fact_states["work_authorization"] = "unknown"
                notes.append("Work authorization status is unknown/unspecified for a role requiring legal authorization.")
            elif auth_status in ("authorized_without_sponsorship", "us_citizen", "permanent_resident", "citizen"):
                loc_score += 50.0
                fact_states["work_authorization"] = "verified"
            elif auth_status in ("requires_sponsorship", "visa_dependent"):
                loc_score += 0.0
                fact_states["work_authorization"] = "conflicting"
                notes.append("Job requires work authorization without sponsorship, but candidate requires sponsorship.")
            else:
                loc_score += 25.0
                fact_states["work_authorization"] = "unverified"
        else:
            # No explicit legal authorization constraint stated in posting
            if auth_status in ("authorized_without_sponsorship", "us_citizen", "permanent_resident", "citizen"):
                loc_score += 50.0
                fact_states["work_authorization"] = "verified"
            elif not auth_status or auth_status == "unknown":
                loc_score += 40.0
                fact_states["work_authorization"] = "unknown"
            else:
                loc_score += 35.0
                fact_states["work_authorization"] = "unverified"

        return min(max(loc_score, 0.0), 100.0), fact_states, notes

    def evaluate_match(
        self,
        candidate_user: User,
        job_posting: JobPosting,
    ) -> MatchBreakdown:
        """
        Calculates a deterministic, reproducible match score between candidate and job posting.
        Returns a complete explainability breakdown.
        """
        profile = candidate_user.profile
        profile_version = profile.profile_version if profile else 1

        # 1. Parse job requirements
        parsed_job = parse_job_requirements(
            title=job_posting.title,
            description=job_posting.description,
            location=job_posting.location,
            work_mode=job_posting.work_mode,
        )

        # 2. Index candidate skills by normalized name
        candidate_skills: Dict[str, Skill] = {}
        for s in candidate_user.skills:
            norm_name = normalize_skill(s.name)
            candidate_skills[norm_name] = s

        # Calculate candidate total years of experience
        cand_total_years = 0.0
        for exp in candidate_user.experiences:
            start = exp.start_date
            end = exp.end_date or date.today()
            if start:
                months = (end.year - start.year) * 12 + (end.month - start.month)
                cand_total_years += max(months / 12.0, 0.25)
        # Fallback to max skill years if experiences empty
        if cand_total_years == 0.0 and candidate_user.skills:
            cand_total_years = max([s.years_experience for s in candidate_user.skills] or [0.0])

        # 3. Calculate Component Scores
        # Component 1: Required Skills (35%)
        s_req, matched_req, missing_req = self.score_required_skills(
            candidate_skills, parsed_job.required_skills
        )

        # Component 2: Role Relevance (25%)
        target_titles = profile.target_job_titles if profile else []
        s_role = self.score_role_relevance(
            job_title=job_posting.title,
            responsibilities_text=parsed_job.responsibilities_text,
            target_job_titles=target_titles,
            experiences=candidate_user.experiences,
        )

        # Component 3: Experience & Seniority (15%)
        s_exp = self.score_experience_seniority(
            candidate_years=cand_total_years,
            required_years=parsed_job.required_experience_years,
            target_seniority=parsed_job.seniority_level,
            experiences=candidate_user.experiences,
        )

        # Component 4: Education & Certifications (10%)
        s_edu = self.score_education_certifications(
            educations=candidate_user.educations,
            certifications=candidate_user.certifications,
            required_edu_level=parsed_job.required_education_level,
            candidate_years=cand_total_years,
        )

        # Component 5: Location & Work Authorization (10%)
        candidate_auth = profile.work_authorization_status if profile else None
        candidate_pref = profile.remote_preference if profile else "flexible"
        candidate_loc = profile.location if profile else None

        s_loc, facts_state, loc_notes = self.score_location_and_work_auth(
            job_work_mode=parsed_job.work_mode,
            job_location=parsed_job.location,
            requires_work_auth=parsed_job.requires_work_authorization,
            candidate_remote_pref=candidate_pref,
            candidate_location=candidate_loc,
            candidate_work_auth_status=candidate_auth,
        )

        # Component 6: Preferred Skills (5%)
        s_pref, matched_pref, missing_pref = self.score_preferred_skills(
            candidate_skills, parsed_job.preferred_skills
        )

        # 4. Weighted Aggregate Total Score
        w = self.weights
        total_raw = (
            w["required_skills"] * s_req
            + w["role_relevance"] * s_role
            + w["experience_seniority"] * s_exp
            + w["education_certifications"] * s_edu
            + w["location_work_authorization"] * s_loc
            + w["preferred_skills"] * s_pref
        )
        total_score = round(min(max(total_raw, 0.0), 100.0), 1)

        # 5. Formulate Human-Readable Explanation
        matched_names = [m["skill"] for m in matched_req]
        summary_lines = [
            f"Overall Match: {total_score}/100.",
            f"• Required Skills ({w['required_skills']*100:.0f}%): {s_req:.1f}/100. Matched: {', '.join(matched_names) if matched_names else 'None'}. Missing: {', '.join(missing_req) if missing_req else 'None'}.",
            f"• Role Relevance ({w['role_relevance']*100:.0f}%): {s_role:.1f}/100 based on target titles and responsibilities.",
            f"• Experience & Seniority ({w['experience_seniority']*100:.0f}%): {s_exp:.1f}/100 ({cand_total_years:.1f}y candidate vs {parsed_job.seniority_level} target).",
            f"• Education & Certifications ({w['education_certifications']*100:.0f}%): {s_edu:.1f}/100.",
            f"• Location & Work Auth ({w['location_work_authorization']*100:.0f}%): {s_loc:.1f}/100 ({' | '.join(loc_notes) if loc_notes else 'Compatible'}).",
            f"• Preferred Skills ({w['preferred_skills']*100:.0f}%): {s_pref:.1f}/100.",
        ]
        explanation = "\n".join(summary_lines)

        return MatchBreakdown(
            total_score=total_score,
            component_scores={
                "required_skills": round(s_req, 1),
                "role_relevance": round(s_role, 1),
                "experience_seniority": round(s_exp, 1),
                "education_certifications": round(s_edu, 1),
                "location_work_authorization": round(s_loc, 1),
                "preferred_skills": round(s_pref, 1),
            },
            weights_used=self.weights.copy(),
            matched_skills=matched_req + matched_pref,
            missing_skills=missing_req,
            missing_preferred_skills=missing_pref,
            candidate_facts_state=facts_state,
            explanation=explanation,
            scoring_version=SCORING_VERSION,
            candidate_profile_version=profile_version,
        )


# Global default engine instance
matching_engine = DeterministicMatchingEngine()
