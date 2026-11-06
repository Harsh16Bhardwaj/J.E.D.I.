"""Compare a private reviewed draft with the member's saved resume evidence."""

import re

from backend.schemas.job_intake import (
    DraftFitReport,
    FitAssessment,
    JobDraftDetail,
    JobRequirement,
    SkillFitFinding,
)
from backend.schemas.learning import ResumeEvidence
from backend.services.skill_vocabulary import (
    BROADER_SKILLS,
    canonical_skill,
    skill_key,
    skill_mentions,
)


def reviewed_requirements(draft: JobDraftDetail) -> list[JobRequirement]:
    reviewed = {}
    for level, skills in (
        ("uncertain", draft.fields.mentioned_skills),
        ("preferred", draft.fields.preferred_skills),
        ("required", draft.fields.required_skills),
    ):
        for skill in skills:
            name = canonical_skill(skill)
            reviewed[skill_key(name)] = (name, level)

    groups: dict[tuple[tuple[str, ...], str], JobRequirement] = {}
    group_keys = set()
    for source in draft.requirements:
        keys = tuple(
            sorted({skill_key(canonical_skill(name)) for name in source.skills})
        )
        if (
            source.match == "any"
            and len(keys) > 1
            and all(key in reviewed and reviewed[key][1] == "uncertain" for key in keys)
        ):
            group = (keys, source.level)
            previous = groups.get(group)
            if previous is None or (source.experience_min_years or 0) > (
                previous.experience_min_years or 0
            ):
                groups[group] = source
            group_keys.update(keys)

    single_sources: dict[tuple[str, str], list[JobRequirement]] = {}
    for source in draft.requirements:
        if source.match == "all" and len(source.skills) == 1:
            key = skill_key(canonical_skill(source.skills[0]))
            single_sources.setdefault((key, source.level), []).append(source)

    singles = []
    for key, (name, level) in reviewed.items():
        if key in group_keys:
            continue
        sources = single_sources.get((key, level), [])
        scoped = [
            source for source in sources if source.experience_min_years is not None
        ]
        strongest = max(
            scoped, key=lambda source: source.experience_min_years or 0, default=None
        )
        original = strongest or (sources[0] if sources else None)
        singles.append(
            JobRequirement(
                level=level,
                match="all",
                skills=[name],
                experience_min_years=original.experience_min_years
                if original
                else None,
                experience_max_years=original.experience_max_years
                if original
                else None,
                text=original.text if original else "From the reviewed draft.",
            )
        )
    return sorted(
        [*groups.values(), *singles],
        key=lambda requirement: ("required", "preferred", "uncertain").index(
            requirement.level
        ),
    )


def explicit_quotes(resume: ResumeEvidence, explicit: set[str]) -> dict[str, str]:
    quotes = {}
    for line in resume.text.splitlines():
        if re.search(r"\b(?:no|not|never|without|unfamiliar|lack)\b", line, re.I):
            continue
        for mention in skill_mentions(line):
            key = skill_key(mention.name)
            if key in explicit and key not in quotes:
                snippet = line[max(0, mention.start - 80) : mention.end + 80].strip()
                quotes[key] = snippet
    return quotes


def assess_documented_fit(report: DraftFitReport) -> FitAssessment:
    required = [
        finding
        for finding in report.findings
        if finding.requirement.level == "required"
    ]
    minimum, total = report.job_minimum_years, report.resume_years
    if minimum is None:
        experience = "not_listed"
    elif total is None:
        experience = "unknown"
    else:
        experience = "meets_minimum" if total >= minimum else "below_minimum"

    score = None
    if not required:
        basis = "Add required skills before calculating a score."
    elif any(finding.status == "needs_review" for finding in required):
        basis = "Confirm the required evidence flagged for review before scoring."
    elif experience == "unknown":
        basis = "Add reviewed total experience to evaluate the listed minimum."
    else:
        coverage = sum(finding.status == "evidenced" for finding in required)
        if experience == "not_listed":
            score = round(100 * coverage / len(required))
            basis = "Based on direct evidence for the required skills."
        else:
            score = round(
                80 * coverage / len(required) + 20 * (experience == "meets_minimum")
            )
            basis = "Required skill evidence contributes 80 points and total years 20."
    return FitAssessment(score=score, basis=basis, role_experience=experience)


def compare_draft(
    draft: JobDraftDetail, resume: ResumeEvidence | None
) -> DraftFitReport:
    report = DraftFitReport(
        has_resume=resume is not None,
        job_minimum_years=draft.fields.experience_min_years,
        resume_years=resume.experience_years if resume else None,
    )
    if resume is None:
        return report

    explicit = {skill_key(canonical_skill(skill)) for skill in resume.explicit_skills}
    inferred = {
        skill_key(canonical_skill(item.skill)): item.evidence
        for item in resume.inferred_skills
    }
    for child, parent in BROADER_SKILLS.items():
        if skill_key(child) in explicit:
            inferred.setdefault(
                skill_key(parent), f"The resume lists the related skill {child}."
            )
    quotes = explicit_quotes(resume, explicit)
    for requirement in reviewed_requirements(draft):
        keys = [skill_key(canonical_skill(skill)) for skill in requirement.skills]
        confirmed = [key for key in keys if key in explicit]
        indirect = [key for key in keys if key not in explicit and key in inferred]
        satisfied = (
            bool(confirmed)
            if requirement.match == "any"
            else len(confirmed) == len(keys)
        )
        note = None
        if satisfied and not requirement.experience_min_years:
            status = "evidenced"
        elif satisfied:
            status = "needs_review"
            note = "A skill is listed, but years using it need confirmation."
        elif confirmed or indirect:
            status = "needs_review"
            note = (
                "Review partial or inferred evidence before counting this requirement."
            )
        else:
            status = "not_evidenced"
            note = "Check whether your resume can document this requirement."
        report.findings.append(
            SkillFitFinding(
                requirement=requirement,
                status=status,
                evidence=[
                    quotes.get(key, f"Listed in reviewed resume skills as {skill}.")
                    for skill, key in zip(requirement.skills, keys, strict=True)
                    if key in confirmed
                ]
                + [f"Inferred: {inferred[key]}" for key in indirect],
                note=note,
            )
        )
    report.assessment = assess_documented_fit(report)
    return report
