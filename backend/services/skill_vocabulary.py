"""Shared job and resume skill vocabulary with separate aliases and relationships."""

import re
import unicodedata
from functools import lru_cache
from typing import NamedTuple

from backend.services.scraper_enrichment import load_taxonomy

BASE_ALIASES = {
    "React": ["react", "react.js", "reactjs"],
    "Next.js": ["next.js", "nextjs"],
    "JavaScript": ["javascript", "ecmascript"],
    "TypeScript": ["typescript"],
    "Python": ["python"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "SQL": ["sql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "Node.js": ["node.js", "nodejs"],
    "FastAPI": ["fastapi"],
    "Django": ["django"],
    "Flask": ["flask"],
    "Git": ["git"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "GCP": ["gcp", "google cloud"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Java": ["java"],
    "C++": ["c++"],
    "C#": ["c#", "csharp"],
    "Go": ["golang"],
    "Rust": ["rust"],
    "Redis": ["redis"],
    "MongoDB": ["mongodb"],
    "Linux": ["linux"],
    "GraphQL": ["graphql"],
    "REST": ["rest", "restful"],
    "Terraform": ["terraform"],
    "CI/CD": ["ci/cd", "continuous integration"],
    "Testing": ["unit testing", "jest", "pytest", "vitest"],
    "Machine Learning": ["machine learning"],
    "System Design": ["system design"],
    "Data Structures": ["data structures"],
}

BROADER_SKILLS = {
    "Supervised Learning": "Machine Learning",
    "Unsupervised Learning": "Machine Learning",
    "Deep Learning": "Machine Learning",
}
ADDITIONAL_ALIASES = {
    "React Native": ["react native", "react-native"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "Supervised Learning": ["supervised learning"],
    "Unsupervised Learning": ["unsupervised learning"],
}


def skill_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


@lru_cache(maxsize=1)
def vocabulary() -> dict[str, str]:
    aliases = {}
    for name, variants in {**BASE_ALIASES, **ADDITIONAL_ALIASES}.items():
        for variant in (name, *variants):
            aliases[skill_key(variant)] = name
    for terms in load_taxonomy()["skills"].values():
        for term in terms:
            aliases.setdefault(skill_key(term), term)
    return aliases


def canonical_skill(value: str) -> str:
    return vocabulary().get(skill_key(value), value.strip())


class SkillMention(NamedTuple):
    name: str
    start: int
    end: int


@lru_cache(maxsize=1)
def _matcher() -> re.Pattern[str]:
    terms = (
        re.escape(term).replace(r"\ ", r"\s+")
        for term in sorted(vocabulary(), key=len, reverse=True)
        if term not in {"go", "r", "rest"}
    )
    return re.compile(rf"(?<!\w)(?:{'|'.join(terms)}|(?-i:REST))(?!\w)", re.I)


def skill_mentions(text: str) -> list[SkillMention]:
    return [
        SkillMention(canonical_skill(match.group()), match.start(), match.end())
        for match in _matcher().finditer(text)
    ]


def skill_names(text: str) -> list[str]:
    found = {mention.name for mention in skill_mentions(text)}
    return [name for name in dict.fromkeys(vocabulary().values()) if name in found]
