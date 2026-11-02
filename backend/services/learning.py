"""Question content loading and evidence-based job skill comparisons."""

import re
from functools import lru_cache
from pathlib import Path

from backend.schemas.learning import QuestionBank, ResumeEvidence
from backend.services.resume import canonical_skill, skill_names

TOPIC_SKILLS = {
    "react-rendering": ["React"],
    "python-fundamentals": ["Python"],
    "fastapi-fundamentals": ["FastAPI"],
    "sql-fundamentals": ["SQL"],
}


@lru_cache
def load_banks() -> dict[str, QuestionBank]:
    banks = {}
    for path in sorted(
        (Path(__file__).resolve().parent.parent / "content").glob("*.json")
    ):
        bank = QuestionBank.model_validate_json(path.read_text())
        if bank.topic_id in banks:
            raise ValueError("Duplicate topic ID")
        banks[bank.topic_id] = bank
    return banks


def compare_skills(
    description: str, skills: list[str], evidence: ResumeEvidence | None
) -> dict:
    requirements: dict[str, dict] = {}
    excluded = set()
    clauses = re.split(
        r"[\n;]|(?<=[.!?])\s+|,?\s+(?:but|however|whereas)\s+"
        r"|,(?=[^,;\n]*\b(?:required|optional|preferred|essential|necessary|a plus)\b)",
        description,
        flags=re.I,
    )
    sentences = []
    for clause in clauses:
        sentences.extend(
            clause.split(",")
            if re.search(r"\b(?:not|no)\b", clause, re.I)
            else [clause]
        )
    for sentence in sentences:
        names = skill_names(sentence)
        if not names:
            continue
        if re.search(
            r"\b(not (?:strictly )?(?:required|needed|necessary|essential)"
            r"|no\b.{0,100}\b(?:required|needed|necessary)"
            r"|don't need|do not need|without requiring)\b",
            sentence,
            re.I,
        ):
            excluded.update(names)
            continue
        if re.search(
            r"\b(preferred|bonus|nice.to.have|a plus|optional|desirable)\b",
            sentence,
            re.I,
        ):
            level = "preferred"
        elif re.search(
            r"\b(must|required|require|requires|essential|need|hands.on|proficien\w*)\b",
            sentence,
            re.I,
        ):
            level = "required"
        else:
            level = "uncertain"
        for name in names:
            if name not in requirements or level == "required":
                requirements[name] = {
                    "skill": name,
                    "requirement": level,
                    "evidence": sentence.strip()[:1000],
                }
    for value in skills:
        name = canonical_skill(value)
        if name and name not in requirements and name not in excluded:
            requirements[name] = {
                "skill": name,
                "requirement": "uncertain",
                "evidence": (
                    "Listed in the job's normalized skill tags; "
                    "confirm requirement in the description."
                ),
            }
    explicit = (
        {canonical_skill(x).casefold() for x in evidence.explicit_skills}
        if evidence
        else set()
    )
    inferred = (
        {canonical_skill(x.skill).casefold() for x in evidence.inferred_skills}
        if evidence
        else set()
    )
    matched, missing = [], []
    for name, requirement in requirements.items():
        if name.casefold() in explicit or name.casefold() in inferred:
            matched.append(
                {
                    **requirement,
                    "source": "explicit" if name.casefold() in explicit else "inferred",
                }
            )
        else:
            topics = [
                topic
                for topic, names in TOPIC_SKILLS.items()
                if name in names and topic in load_banks()
            ]
            missing.append({**requirement, "topicIds": topics})
    return {"hasResume": evidence is not None, "matched": matched, "missing": missing}
