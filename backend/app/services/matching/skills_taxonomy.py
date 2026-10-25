"""Transparent, deterministic skills taxonomy and synonym normalization."""

import re
from typing import Dict, List, Optional, Set

# Canonical skill name -> list of aliases, synonyms, and variations (lowercased)
SKILL_SYNONYMS: Dict[str, List[str]] = {
    # Languages
    "python": ["python", "py", "python3", "python 3", "cpython"],
    "javascript": ["javascript", "js", "ecmascript", "es6", "es2020", "esnext"],
    "typescript": ["typescript", "ts"],
    "golang": ["golang", "go lang", "go language", "go"],
    "rust": ["rust", "rustlang"],
    "java": ["java", "java 8", "java 11", "java 17", "java 21"],
    "csharp": ["c#", "csharp", "c-sharp", ".net", "dotnet", "asp.net"],
    "cpp": ["c++", "cpp", "cplusplus"],
    "c": ["c language", "ansi c"],
    "ruby": ["ruby", "ruby on rails", "rails"],
    "php": ["php", "php8", "laravel", "symfony"],
    "scala": ["scala"],
    "kotlin": ["kotlin"],
    "swift": ["swift", "swiftui"],

    # Frontend
    "react": ["react", "react.js", "reactjs", "react native"],
    "nextjs": ["next.js", "nextjs", "next"],
    "vue": ["vue", "vue.js", "vuejs", "vue3", "nuxt"],
    "angular": ["angular", "angularjs", "angular 2+"],
    "svelte": ["svelte", "sveltekit"],
    "html": ["html", "html5"],
    "css": ["css", "css3", "sass", "scss", "less"],
    "tailwind": ["tailwind", "tailwindcss", "tailwind css"],
    "redux": ["redux", "redux toolkit", "rtk"],

    # Backend & APIs
    "fastapi": ["fastapi", "fast-api"],
    "django": ["django", "django rest framework", "drf"],
    "flask": ["flask"],
    "express": ["express", "express.js", "expressjs"],
    "nodejs": ["node", "node.js", "nodejs"],
    "nestjs": ["nestjs", "nest.js"],
    "spring": ["spring", "spring boot", "springboot"],
    "graphql": ["graphql", "apollo graphql"],
    "rest_api": ["rest", "restful", "rest api", "rest apis", "restful api", "web api"],
    "grpc": ["grpc", "protobuf", "protocol buffers"],

    # Databases & Storage
    "postgresql": ["postgresql", "postgres", "psql"],
    "mysql": ["mysql", "mariadb"],
    "sqlite": ["sqlite", "sqlite3"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis", "in-memory cache", "valkey"],
    "elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
    "dynamodb": ["dynamodb", "aws dynamodb"],
    "cassandra": ["cassandra"],
    "sql": ["sql", "rdbms", "relational database"],
    "nosql": ["nosql", "no-sql", "document database"],

    # Cloud & Infrastructure
    "aws": ["aws", "amazon web services", "amazon cloud", "ec2", "s3", "lambda"],
    "gcp": ["gcp", "google cloud", "google cloud platform", "google cloud platform (gcp)"],
    "azure": ["azure", "microsoft azure"],
    "docker": ["docker", "containerization", "dockerfile", "containers"],
    "kubernetes": ["kubernetes", "k8s", "helm"],
    "terraform": ["terraform", "iac", "infrastructure as code"],
    "ansible": ["ansible"],
    "ci_cd": ["ci/cd", "cicd", "continuous integration", "continuous deployment", "github actions", "gitlab ci", "jenkins"],
    "linux": ["linux", "unix", "ubuntu", "debian", "redhat", "centos", "bash", "shell scripting"],

    # Architecture & Practices
    "microservices": ["microservices", "micro-services", "microservice architecture"],
    "distributed_systems": ["distributed systems", "distributed computing", "high availability", "scalability"],
    "system_design": ["system design", "software architecture", "technical design"],
    "agile": ["agile", "scrum", "kanban", "sprint planning"],
    "testing": ["unit testing", "integration testing", "e2e testing", "pytest", "jest", "vitest", "tdd"],
    "kafka": ["kafka", "apache kafka", "event streaming", "event-driven architecture"],
    "rabbitmq": ["rabbitmq", "message queue", "amqp"],

    # Data & AI / ML
    "machine_learning": ["machine learning", "ml", "deep learning", "ai", "artificial intelligence"],
    "pandas": ["pandas", "numpy", "scipy"],
    "pytorch": ["pytorch", "torch"],
    "tensorflow": ["tensorflow", "keras"],
    "llm": ["llm", "large language models", "generative ai", "langchain", "langgraph", "rag"],
    "data_engineering": ["data engineering", "etl", "data pipelines", "spark", "airflow", "databricks"],
}

# Inverted index: alias (lowercase) -> canonical skill
_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in SKILL_SYNONYMS.items():
    _ALIAS_TO_CANONICAL[canonical] = canonical
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower().strip()] = canonical


def normalize_skill(skill_name: str) -> str:
    """
    Normalizes a skill name to its canonical taxonomy identifier.
    If no alias match exists, returns cleaned, lowercased string.
    """
    if not skill_name or not isinstance(skill_name, str):
        return ""

    cleaned = skill_name.strip().lower()
    # Strip common prefixes/suffixes e.g. "proficient in python" -> "python"
    cleaned = re.sub(r"^(knowledge of|experience with|proficient in|skilled in)\s+", "", cleaned)
    cleaned = cleaned.strip()

    # Exact match in alias mapping
    if cleaned in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[cleaned]

    # Handle punctuation variations (e.g. "react-js" -> "react.js")
    cleaned_punct = cleaned.replace("-", " ").replace("_", " ")
    if cleaned_punct in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[cleaned_punct]

    return cleaned


def extract_skills_from_text(text: str) -> Set[str]:
    """
    Extracts all known canonical skills appearing in text using word boundaries
    to prevent substring false positives (e.g. 'go' in 'good').
    """
    if not text:
        return set()

    found_skills: Set[str] = set()
    lowered = text.lower()

    for canonical, aliases in SKILL_SYNONYMS.items():
        for alias in aliases:
            # Special case for symbols like c++, c#, .net
            if alias in ("c++", "c#", ".net"):
                escaped = re.escape(alias)
                pattern = rf"(?:^|[\s,;/()]){escaped}(?:$|[\s,;/()])"
            else:
                escaped = re.escape(alias)
                pattern = rf"\b{escaped}\b"

            if re.search(pattern, lowered):
                found_skills.add(canonical)
                break

    return found_skills
