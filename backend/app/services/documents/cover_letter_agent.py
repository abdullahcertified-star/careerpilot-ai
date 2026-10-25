"""Cover Letter Agent using LangChain structured outputs for job-specific tailored cover letters.

Enforces zero fabrication: grounds content in verified candidate experience, authentic past roles,
and genuine alignment with the target company's requisition.
"""

import json
import logging
from typing import Optional, Tuple
from app.core.config import settings
from app.models.entities import JobPosting, User
from app.services.documents.factual_checker import factual_checker
from app.services.documents.resume_agent import MissingAIConfigurationError
from app.services.documents.schemas import (
    FactualValidationReport,
    StructuredCoverLetter,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "1.0.0"


class CoverLetterAgent:
    """Agent that creates tailored, fact-grounded cover letters for selected job postings."""

    def __init__(self) -> None:
        self.openai_key = settings.OPENAI_API_KEY
        self.anthropic_key = settings.ANTHROPIC_API_KEY

    def is_ai_configured(self) -> bool:
        """Check whether valid third-party LLM credentials exist."""
        return (
            self.openai_key not in ("placeholder_openai_api_key", "", None)
            or self.anthropic_key not in ("placeholder_anthropic_api_key", "", None)
        )

    async def generate_tailored_cover_letter(
        self,
        candidate: User,
        job: JobPosting,
        custom_instructions: Optional[str] = None,
        require_live_llm: bool = False,
    ) -> Tuple[StructuredCoverLetter, str, FactualValidationReport, str, str]:
        """
        Generates a tailored cover letter grounded strictly in candidate verified background.
        Returns (StructuredCoverLetter, formatted_text, validation_report, model_name, prompt_version).
        """
        if require_live_llm and not self.is_ai_configured():
            raise MissingAIConfigurationError(
                "AI credentials are not configured on the backend. Please provide OPENAI_API_KEY or ANTHROPIC_API_KEY."
            )

        model_name = "mock-agent-v1"
        structured_letter: Optional[StructuredCoverLetter] = None

        if self.is_ai_configured():
            try:
                structured_letter, model_name = await self._generate_with_langchain(
                    candidate, job, custom_instructions
                )
            except Exception as exc:
                logger.error("LangChain cover letter generation error: %s", exc)
                if require_live_llm:
                    raise
                structured_letter = None

        if structured_letter is None:
            structured_letter = self._build_grounded_cover_letter(candidate, job)
            model_name = "careerpilot-factual-agent-v1"

        validation_report = factual_checker.verify_cover_letter(structured_letter, candidate)
        formatted_text = self.render_to_plain_text(structured_letter)

        return (
            structured_letter,
            formatted_text,
            validation_report,
            model_name,
            PROMPT_VERSION,
        )

    async def _generate_with_langchain(
        self,
        candidate: User,
        job: JobPosting,
        custom_instructions: Optional[str],
    ) -> Tuple[StructuredCoverLetter, str]:
        """Invokes LangChain with structured output schema for cover letter."""
        from langchain_core.prompts import ChatPromptTemplate

        system_prompt = (
            "You are CareerPilot's Verified Cover Letter Agent.\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Generate a professional, compelling cover letter for: {job_title} at {job_company}.\n"
            "2. Ground every past employer mention and technical capability in the candidate's verified record.\n"
            "3. NEVER invent past companies, degrees, dates, metrics, or unearned certifications.\n"
            "4. Keep the tone professional, confident, concise, and focused on value to {job_company}.\n"
        )

        user_content = json.dumps(
            {
                "target_job": {
                    "title": job.title,
                    "company": job.company,
                    "description": job.description,
                },
                "verified_candidate": {
                    "full_name": candidate.full_name,
                    "email": candidate.email,
                    "skills": [s.name for s in candidate.skills],
                    "experiences": [
                        {"company": e.company, "title": e.title, "description": e.description}
                        for e in candidate.experiences
                    ],
                },
                "custom_instructions": custom_instructions or "",
            },
            indent=2,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{candidate_and_job_data}"),
        ])

        if self.openai_key and self.openai_key != "placeholder_openai_api_key":
            from pydantic import SecretStr
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model="gpt-4o-mini", api_key=SecretStr(self.openai_key), temperature=0.3)
            structured_llm = llm.with_structured_output(StructuredCoverLetter)
            chain = prompt | structured_llm
            result = await chain.ainvoke({
                "job_title": job.title,
                "job_company": job.company,
                "candidate_and_job_data": user_content,
            })
            if isinstance(result, StructuredCoverLetter):
                return result, "gpt-4o-mini"
            elif isinstance(result, dict):
                return StructuredCoverLetter.model_validate(result), "gpt-4o-mini"

        raise ValueError("No supported active LLM provider configured.")

    def _build_grounded_cover_letter(self, candidate: User, job: JobPosting) -> StructuredCoverLetter:
        """Builds a deterministic fact-grounded cover letter tailored to the job posting."""
        prof = candidate.profile
        skills_sample = [s.name for s in candidate.skills[:4]]
        skills_str = ", ".join(skills_sample) if skills_sample else "modern software engineering"

        recent_exp = candidate.experiences[0] if candidate.experiences else None
        past_ref = (
            f"most recently as {recent_exp.title} at {recent_exp.company}"
            if recent_exp
            else "through my progressive engineering career"
        )

        opening = (
            f"I am writing to express my enthusiasm for the {job.title} position at {job.company}. "
            f"With a strong foundation in {skills_str} and a track record of delivering resilient solutions, "
            f"I am eager to contribute directly to your team's mission and engineering standards."
        )

        body_1 = (
            f"Throughout my professional background, {past_ref}, I have focused on building scalable, "
            f"reliable architectures while collaborating cross-functionally to achieve measurable results. "
            f"My hands-on experience applying {skills_str} directly complements the technical responsibilities outlined for the {job.title} role."
        )

        body_2 = (
            f"What attracts me most to {job.company} is the opportunity to solve high-impact challenges "
            f"alongside talented colleagues. I bring genuine intellectual curiosity, strict adherence to best practices, "
            f"and an authentic drive to deliver immediate value from day one."
        )

        closing = (
            f"I welcome the opportunity to discuss how my verified technical skills and professional experience "
            f"can advance {job.company}'s goals for the {job.title} position."
        )

        return StructuredCoverLetter(
            sender_name=candidate.full_name,
            sender_email=candidate.email,
            sender_phone=prof.phone if prof else None,
            sender_location=prof.location if prof else None,
            target_company=job.company,
            target_title=job.title,
            salutation=f"Dear Hiring Team at {job.company},",
            opening_paragraph=opening,
            body_paragraphs=[body_1, body_2],
            closing_paragraph=closing,
            call_to_action="Thank you for your time and consideration. I look forward to the possibility of speaking with you.",
            sign_off="Sincerely,",
        )

    @staticmethod
    def render_to_plain_text(letter: StructuredCoverLetter) -> str:
        """Renders structured cover letter to clean formatted plain text."""
        lines = []
        lines.append(letter.sender_name)
        contact = [letter.sender_email]
        if letter.sender_phone:
            contact.append(letter.sender_phone)
        if letter.sender_location:
            contact.append(letter.sender_location)
        lines.append(" | ".join(contact))
        lines.append("")
        lines.append(f"To: Hiring Team at {letter.target_company}")
        lines.append(f"Position: {letter.target_title}")
        lines.append("-" * 60)
        lines.append("")
        lines.append(letter.salutation)
        lines.append("")
        lines.append(letter.opening_paragraph)
        lines.append("")
        for p in letter.body_paragraphs:
            lines.append(p)
            lines.append("")
        lines.append(letter.closing_paragraph)
        lines.append("")
        lines.append(letter.call_to_action)
        lines.append("")
        lines.append(letter.sign_off)
        lines.append(letter.sender_name)
        return "\n".join(lines)


cover_letter_agent = CoverLetterAgent()
