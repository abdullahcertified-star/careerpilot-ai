"""Development seed script with fictional candidate data only.

Usage:
    python backend/scripts/seed.py
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
import logging
import os
import sys

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import hash_password
from app.models.entities import (
    Certification,
    Education,
    Experience,
    Profile,
    Project,
    Skill,
    User,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def seed_database() -> None:
    """Seed database with fictional candidate data."""
    logger.info("Starting development seed process...")

    async with async_session_factory() as session:
        # Check if seed user already exists
        stmt = select(User).where(User.email == "alex.morgan@example.com")
        existing_user = (await session.execute(stmt)).scalar_one_or_none()

        if existing_user:
            logger.info("Fictional seed candidate already exists in database. Skipping seed.")
            return

        # 1. Primary Fictional Candidate: Alex Morgan
        candidate = User(
            email="alex.morgan@example.com",
            hashed_password=hash_password("CareerPilot2026!"),
            full_name="Alex Morgan",
            role="candidate",
            is_active=True,
            is_verified=True,
        )
        session.add(candidate)
        await session.flush()

        profile = Profile(
            user_id=candidate.id,
            headline="Lead AI Systems & Full Stack Architect",
            bio="Passionate engineer building autonomous agent architectures, distributed Python services, and resilient user experiences.",
            location="San Francisco, CA (Remote)",
            phone="+1 (555) 019-2834",
            github_url="https://github.com/alexmorgan-mock",
            linkedin_url="https://linkedin.com/in/alexmorgan-mock",
            website_url="https://alexmorgan.dev.mock",
            target_job_titles=["Lead AI Architect", "Staff Software Engineer", "Full Stack Tech Lead"],
            target_salary_min=180000,
            target_salary_max=240000,
            remote_preference="remote",
        )
        session.add(profile)

        # Skills
        skills_data = [
            ("Python", "technical", "expert", 8.0),
            ("FastAPI", "technical", "expert", 5.0),
            ("TypeScript", "technical", "advanced", 6.0),
            ("Next.js", "technical", "advanced", 4.0),
            ("LangGraph & LangChain", "technical", "advanced", 2.0),
            ("PostgreSQL & SQLAlchemy", "technical", "expert", 7.0),
            ("Redis & Async Workers", "technical", "advanced", 5.0),
            ("System Architecture", "domain", "expert", 8.0),
        ]
        for name, category, proficiency, exp_years in skills_data:
            session.add(
                Skill(
                    user_id=candidate.id,
                    name=name,
                    category=category,
                    proficiency_level=proficiency,
                    years_experience=exp_years,
                )
            )

        # Education
        session.add(
            Education(
                user_id=candidate.id,
                institution="Tech State University",
                degree="Bachelor of Science",
                field_of_study="Computer Science & Intelligent Systems",
                start_date=date(2015, 9, 1),
                end_date=date(2019, 5, 20),
                is_current=False,
                gpa="3.9",
            )
        )

        # Experience
        session.add(
            Experience(
                user_id=candidate.id,
                company="Nexus Platform Labs",
                title="Staff Software Architect",
                location="Remote",
                start_date=date(2022, 6, 1),
                end_date=None,
                is_current=True,
                description="Led design and implementation of autonomous agent pipelines and high-throughput microservices.",
                achievements=[
                    "Architected distributed agent workflow processing 100k+ tasks daily with 99.9% uptime",
                    "Reduced end-to-end API latency by 45% using async connection pooling and Redis caching",
                ],
            )
        )
        session.add(
            Experience(
                user_id=candidate.id,
                company="Synthetix Technologies",
                title="Senior Full Stack Engineer",
                location="San Francisco, CA",
                start_date=date(2019, 6, 15),
                end_date=date(2022, 5, 30),
                is_current=False,
                description="Built interactive web dashboards and secure authentication layers.",
                achievements=[
                    "Spearheaded Next.js migration improving Core Web Vitals across candidate portals",
                ],
            )
        )

        # Projects
        session.add(
            Project(
                user_id=candidate.id,
                title="Autonomous Career Assistant Engine",
                description="State-machine driven job matcher and resume optimization graph.",
                url="https://demo.careerpilot.mock",
                repo_url="https://github.com/alexmorgan-mock/agent-pipeline",
                technologies=["FastAPI", "LangGraph", "TypeScript", "Tailwind CSS"],
                start_date=date(2024, 1, 1),
                end_date=None,
            )
        )

        # Certifications
        session.add(
            Certification(
                user_id=candidate.id,
                name="AWS Certified Solutions Architect - Professional",
                issuer="Amazon Web Services",
                issue_date=date(2023, 4, 15),
                expiration_date=date(2026, 4, 15),
                credential_id="AWS-PSA-991283",
                credential_url="https://aws.amazon.com/verify/AWS-PSA-991283",
            )
        )

        # 2. Secondary Fictional Candidate: Jordan Lee (for isolation & ownership testing)
        candidate_2 = User(
            email="jordan.lee@example.com",
            hashed_password=hash_password("CareerPilot2026!"),
            full_name="Jordan Lee",
            role="candidate",
            is_active=True,
            is_verified=True,
        )
        session.add(candidate_2)
        await session.flush()

        profile_2 = Profile(
            user_id=candidate_2.id,
            headline="Frontend Engineer & Design Systems Specialist",
            bio="Crafting pixel-perfect, accessible, and fast web experiences with React, Next.js, and modern CSS.",
            location="New York, NY",
            phone="+1 (555) 012-7788",
            target_job_titles=["Senior Frontend Engineer", "UI Engineer"],
            target_salary_min=140000,
            target_salary_max=180000,
            remote_preference="hybrid",
        )
        session.add(profile_2)

        session.add(
            Skill(
                user_id=candidate_2.id,
                name="React & Next.js",
                category="technical",
                proficiency_level="expert",
                years_experience=5.0,
            )
        )

        await session.commit()
        logger.info("Development database seeded successfully with 2 fictional candidate profiles!")


if __name__ == "__main__":
    asyncio.run(seed_database())
