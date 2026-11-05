"""Conservative extraction from a pasted job description."""

import re

from backend.schemas.job_intake import (
    JobDraftFields,
    JobEvidence,
    JobPreview,
    JobRequirement,
)
from backend.services.scraper_enrichment import extract_facts
from backend.services.skill_vocabulary import SkillMention, skill_mentions

LABELS = {
    "job title": "title",
    "role title": "title",
    "title": "title",
    "company": "employer",
    "employer": "employer",
    "location": "location",
    "work mode": "work_mode",
    "work arrangement": "work_mode",
    "employment type": "employment_type",
}
WORK_MODES = {
    "remote": "REMOTE",
    "hybrid": "HYBRID",
    "on-site": "ON_SITE",
    "onsite": "ON_SITE",
    "on site": "ON_SITE",
}
SECTIONS = {
    "requirements": "required_skills",
    "required skills": "required_skills",
    "required qualifications": "required_skills",
    "minimum qualifications": "required_skills",
    "must have": "required_skills",
    "must-have": "required_skills",
    "preferred skills": "preferred_skills",
    "preferred qualifications": "preferred_skills",
    "nice to have": "preferred_skills",
    "nice-to-have": "preferred_skills",
    "responsibilities": "responsibilities",
    "what you'll do": "responsibilities",
    "what you’ll do": "responsibilities",
    "qualifications": "mentioned_skills",
    "skills": "mentioned_skills",
    "about us": "mentioned_skills",
    "about the role": "mentioned_skills",
    "benefits": "mentioned_skills",
    "compensation": "mentioned_skills",
}


NEGATED = re.compile(
    r"\b(?:not (?:strictly )?(?:required|necessary|needed)|no experience|"
    r"no\b.{0,80}\b(?:experience|skills?)\b.{0,40}\b(?:required|needed)|"
    r"do not require|don't require)\b",
    re.I,
)
YEARS = re.compile(
    r"(?<![\d.])(?P<min>\d{1,2}(?:\.\d{1,2})?)"
    r"(?:\s*(?:[-–—]|to)\s*(?P<max>\d{1,2}(?:\.\d{1,2})?)|\s*\+)?"
    r"\s+years?\b",
    re.I,
)
TITLE = re.compile(
    r"[\w][\w .+#/&–-]{0,86}\b(?:engineer|developer|scientist|analyst|designer|"
    r"manager|architect|specialist|consultant|intern)(?:\s+(?:[IVX]{1,4}|[1-4]))?",
    re.I,
)
CLAUSE_BREAK = re.compile(r";|(?<=[.!?])\s+(?=[A-Z])|,?\s+\b(?:but|whereas)\b\s+", re.I)


def skill_section(text: str, section: str) -> str:
    required = re.search(r"\b(?:must(?: have)?|required|mandatory)\b", text, re.I)
    preferred = re.search(
        r"\b(?:preferred|nice[- ]to[- ]have|a plus|optional|bonus|desirable)\b",
        text,
        re.I,
    )
    if required and preferred:
        return "mentioned_skills"
    if required:
        return "required_skills"
    if preferred:
        return "preferred_skills"
    return section if section != "responsibilities" else "mentioned_skills"


def experience_range(text: str) -> tuple[float, float | None] | None:
    matches = list(YEARS.finditer(text))
    if len(matches) != 1:
        return None
    minimum = float(matches[0]["min"])
    maximum = float(matches[0]["max"]) if matches[0]["max"] else None
    if 0 <= minimum <= (maximum if maximum is not None else 80) <= 80:
        return minimum, maximum
    return None


def experience_attaches(
    text: str, years: re.Match[str], skill: SkillMention, *, alternative: bool
) -> bool:
    if years.end() <= skill.start:
        return bool(
            re.fullmatch(
                r"\s+(?:(?:of\s+)?(?:hands-on\s+)?experience\s+)?"
                r"(?:of|with|in|using)\s+",
                text[years.end() : skill.start],
                re.I,
            )
        )
    return (
        not alternative
        and skill.end <= years.start()
        and bool(re.fullmatch(r"[\s:(–-]*", text[skill.end : years.start()]))
    )


def preview_job(description: str) -> JobPreview:
    fields = JobDraftFields()
    evidence: list[JobEvidence] = []
    warnings: list[str] = []
    labeled: dict[str, dict[str, str]] = {}
    skills: dict[str, dict[str, str]] = {}
    general_experience: dict[tuple[float, float | None], str] = {}
    unclear_experience = False
    requirements: list[JobRequirement] = []
    section = "mentioned_skills"
    lines = [
        line
        for raw in description.splitlines()
        if (line := raw.strip().lstrip("•*-# ").strip())
    ]
    for line in lines:
        heading, delimiter, remainder = line.partition(":")
        key = heading.casefold().strip()
        value = remainder.strip()
        if delimiter and key in LABELS and value:
            labeled.setdefault(LABELS[key], {})[value] = line[:400]
            continue
        if key in SECTIONS:
            section = SECTIONS[key]
            line = value
        if not line:
            continue
        if section == "responsibilities" and len(fields.responsibilities) < 40:
            fields.responsibilities.append(line[:1_000])
        for clause in CLAUSE_BREAK.split(line):
            negated = bool(NEGATED.search(clause))
            bucket = skill_section(clause, section)
            mentions = skill_mentions(clause)
            names = list(dict.fromkeys(mention.name for mention in mentions))
            years_match = YEARS.search(clause) if not negated else None
            years = experience_range(clause) if years_match else None
            between_skills = (
                clause[mentions[0].end : mentions[-1].start]
                if len(mentions) > 1
                else ""
            )
            alternatives = bool(
                re.search(r"\b(?:or|either|one of)\b", clause, re.I)
                or "/" in between_skills
            )
            simple_choice = (
                alternatives
                and len(names) == 2
                and not re.search(r"\band\b|/", clause, re.I)
                and bool(re.search(r"\bor\b", between_skills, re.I))
            )
            scoped_years = None
            if years_match and years:
                if not names or (
                    (len(names) == 1 or simple_choice)
                    and experience_attaches(
                        clause, years_match, mentions[0], alternative=simple_choice
                    )
                ):
                    scoped_years = years
            if years_match:
                if (
                    years
                    and not names
                    and not alternatives
                    and (
                        bucket == "required_skills"
                        or (
                            bucket == "mentioned_skills"
                            and section == "mentioned_skills"
                            and bool(re.search(r"\bexperience\b", clause, re.I))
                        )
                    )
                ):
                    general_experience.setdefault(years, clause.strip()[:400])
                elif not names or scoped_years is None:
                    unclear_experience = True
            if not negated and (names or years) and len(requirements) < 100:
                level = {
                    "required_skills": "required",
                    "preferred_skills": "preferred",
                }.get(bucket, "uncertain")
                match = "any" if simple_choice else "review" if alternatives else "all"
                requirement = JobRequirement(
                    level=level,
                    match=match,
                    skills=names,
                    experience_min_years=scoped_years[0] if scoped_years else None,
                    experience_max_years=scoped_years[1] if scoped_years else None,
                    text=clause.strip()[:1000],
                )
                if requirement not in requirements:
                    requirements.append(requirement)
            if negated or alternatives:
                bucket = "mentioned_skills"
            for mention in mentions:
                snippet = clause[
                    max(0, mention.start - 130) : mention.end + 130
                ].strip()
                skills.setdefault(mention.name, {}).setdefault(bucket, snippet)

    if lines and "title" not in labeled:
        heading = lines[0]
        if TITLE.fullmatch(heading) and not re.match(
            r"(?:we |you |our |hiring |seeking |looking |join )", heading, re.I
        ):
            fields.title = heading
            evidence.append(JobEvidence(field="title", text=heading, inferred=True))
            warnings.append("Review the suggested title from the first line.")

    for field, values in labeled.items():
        if len(values) != 1:
            warnings.append(f"Multiple {field.replace('_', ' ')} values were found.")
            continue
        value, snippet = next(iter(values.items()))
        if field == "work_mode":
            value = WORK_MODES.get(value.casefold())
            if value is None:
                warnings.append("Review the work arrangement in the original text.")
                continue
        setattr(fields, field, value[:300])
        evidence.append(JobEvidence(field=field, text=snippet))

    for name, sightings in skills.items():
        classifications = set(sightings) - {"mentioned_skills"}
        bucket = (
            next(iter(classifications))
            if len(classifications) == 1
            else "mentioned_skills"
        )
        if len(getattr(fields, bucket)) >= 100:
            continue
        getattr(fields, bucket).append(name)
        evidence.append(
            JobEvidence(
                field=name, text=sightings.get(bucket) or next(iter(sightings.values()))
            )
        )

    if len(general_experience) == 1:
        years, snippet = next(iter(general_experience.items()))
        fields.experience_min_years, fields.experience_max_years = years
        evidence.append(JobEvidence(field="experience", text=snippet))
    if len(general_experience) > 1 or unclear_experience:
        warnings.append("Review experience in the original text for a confirmed range.")
    extracted = extract_facts(re.sub(r"\d{32,}", " ", description))
    for item in extracted.evidence:
        field, snippet = item["field"], item["text"]
        if (
            field == "employmentType"
            and extracted.facts[field]
            and not fields.employment_type
        ):
            fields.employment_type = snippet[:300]
            evidence.append(JobEvidence(field="employment type", text=snippet))
        if field == "education" and extracted.facts[field]:
            fields.education = snippet[:300]
            evidence.append(JobEvidence(field="education", text=snippet))
        if field == "workAuthorizationRequired":
            matches = [
                line.strip()
                for line in description.splitlines()
                if snippet.casefold() in line.casefold()
            ]
            if len(matches) == 1 and len(matches[0]) <= 300:
                fields.authorization = matches[0]
            evidence.append(
                JobEvidence(field="authorization", text=fields.authorization or snippet)
            )
        if field == "salary":
            fields.compensation = snippet[:300]
            evidence.append(JobEvidence(field="compensation", text=snippet))
    if extracted.closed_or_disabled:
        warnings.append("The pasted text indicates that applications may be closed.")
    return JobPreview(
        fields=fields, evidence=evidence, warnings=warnings, requirements=requirements
    )
