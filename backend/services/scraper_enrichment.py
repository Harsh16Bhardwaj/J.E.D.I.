"""Deterministic, evidence-backed extraction for scraper candidates."""

from __future__ import annotations

import hashlib
import html
import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

TAXONOMY_PATH = Path(__file__).parents[1] / "scraper_taxonomy.toml"


@dataclass(frozen=True)
class ExtractionResult:
    version: str
    facts: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]
    description_fingerprint: str
    boilerplate_suspected: bool
    closed_or_disabled: bool


@lru_cache
def load_taxonomy() -> dict[str, Any]:
    return tomllib.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def normalized_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _evidence(
    field: str, value: Any, match: re.Match[str], rule: str, text: str
) -> dict[str, Any]:
    start, end = match.span()
    return {
        "field": field,
        "value": value,
        "start": start,
        "end": end,
        "text": text[start:end],
        "rule": rule,
    }


def _term_matches(text: str, term: str) -> list[re.Match[str]]:
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    return list(re.finditer(pattern, text, flags=re.IGNORECASE))


def _single_fact(
    field: str,
    choices: dict[str, list[str]],
    text: str,
    evidence: list[dict[str, Any]],
) -> str | None:
    found: list[str] = []
    for value, terms in choices.items():
        for term in terms:
            matches = _term_matches(text, term)
            if matches:
                found.append(value)
                evidence.append(
                    _evidence(
                        field, value, matches[0], f"taxonomy:{field}:{value}", text
                    )
                )
                break
    unique = list(dict.fromkeys(found))
    return unique[0] if len(unique) == 1 else None


def extract_facts(description: Any) -> ExtractionResult:
    taxonomy = load_taxonomy()
    text = normalized_text(description)
    evidence: list[dict[str, Any]] = []
    skill_groups: dict[str, list[str]] = {}
    for group, terms in taxonomy.get("skills", {}).items():
        values: list[str] = []
        for term in terms:
            matches = _term_matches(text, str(term))
            if not matches:
                continue
            values.append(str(term))
            evidence.append(
                _evidence(
                    "skills", str(term), matches[0], f"taxonomy:skills:{group}", text
                )
            )
        skill_groups[group] = values

    ranges: list[tuple[float, float | None, re.Match[str]]] = []
    for pattern in (
        r"(?P<min>\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(?P<max>\d+(?:\.\d+)?)\s+years?",
        r"(?P<min>\d+(?:\.\d+)?)\s*\+\s*years?",
        r"(?:minimum|min\.?|at least)\s*(?P<min>\d+(?:\.\d+)?)\s+years?",
    ):
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            ranges.append(
                (
                    float(match.group("min")),
                    float(match.group("max")) if match.groupdict().get("max") else None,
                    match,
                )
            )
    experience_min: float | None = None
    experience_max: float | None = None
    if ranges:
        distinct = {(minimum, maximum) for minimum, maximum, _ in ranges}
        if len(distinct) == 1:
            experience_min, experience_max = next(iter(distinct))
            match = ranges[0][2]
            evidence.append(
                _evidence(
                    "experienceRange",
                    {"min": experience_min, "max": experience_max},
                    match,
                    "experience:explicit-range",
                    text,
                )
            )

    employment_choices = {
        key.replace("_", "-").upper(): [str(item) for item in values]
        for key, values in taxonomy.get("employment", {}).items()
    }
    employment_type = _single_fact("employmentType", employment_choices, text, evidence)
    education_choices = {
        key.upper(): [str(item) for item in values]
        for key, values in taxonomy.get("education", {}).items()
    }
    education = _single_fact("education", education_choices, text, evidence)

    authorization_matches: list[re.Match[str]] = []
    for phrase in taxonomy.get("work_authorization", {}).get("required", []):
        authorization_matches.extend(_term_matches(text, str(phrase)))
    work_authorization_required: bool | None = None
    if authorization_matches:
        work_authorization_required = True
        evidence.append(
            _evidence(
                "workAuthorizationRequired",
                True,
                authorization_matches[0],
                "authorization:explicit-required",
                text,
            )
        )

    restriction_pattern = re.compile(
        r"(?:remote\s+(?:only\s+)?(?:within|in|from)|must\s+"
        r"(?:live|reside|be located)\s+in)\s+"
        r"(?P<region>the united states|u\.?s\.?|canada|europe|emea|"
        r"united kingdom|uk|australia)",
        flags=re.IGNORECASE,
    )
    restrictions = []
    for match in restriction_pattern.finditer(text):
        region = match.group("region")
        restrictions.append(region)
        evidence.append(
            _evidence(
                "remoteCountryRestrictions",
                region,
                match,
                "remote:explicit-country-restriction",
                text,
            )
        )

    seniority_matches = []
    for term in ("senior", "staff", "principal", "lead", "manager", "director"):
        seniority_matches.extend((term, match) for match in _term_matches(text, term))
    seniority = None
    if seniority_matches:
        values = list(dict.fromkeys(value for value, _ in seniority_matches))
        if len(values) == 1:
            seniority = values[0].upper()
            evidence.append(
                _evidence(
                    "seniority",
                    seniority,
                    seniority_matches[0][1],
                    "seniority:explicit-description",
                    text,
                )
            )

    salary = _salary_fact(text, evidence)
    lower = text.casefold()
    closed_or_disabled = any(
        phrase in lower
        for phrase in (
            "position has been filled",
            "job is no longer available",
            "applications are closed",
            "no longer accepting applications",
        )
    )
    company_words = sum(
        lower.count(phrase)
        for phrase in ("our company", "our mission", "we are a company", "about us")
    )
    vacancy_words = sum(
        lower.count(phrase)
        for phrase in (
            "responsibilities",
            "requirements",
            "you will",
            "what you'll do",
            "qualifications",
        )
    )
    boilerplate_suspected = (
        len(text) >= 300 and company_words >= 2 and vacancy_words == 0
    )
    fingerprint_source = re.sub(r"[^a-z0-9]+", " ", lower).strip()
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    facts = {
        "skills": [value for values in skill_groups.values() for value in values],
        "skillsByGroup": skill_groups,
        "experienceMinYears": experience_min,
        "experienceMaxYears": experience_max,
        "seniority": seniority,
        "employmentType": employment_type,
        "remoteCountryRestrictions": restrictions,
        "salary": salary,
        "education": education,
        "workAuthorizationRequired": work_authorization_required,
    }
    return ExtractionResult(
        version=str(taxonomy["version"]),
        facts=facts,
        evidence=tuple(evidence),
        description_fingerprint=fingerprint,
        boilerplate_suspected=boilerplate_suspected,
        closed_or_disabled=closed_or_disabled,
    )


def _salary_fact(text: str, evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
    pattern = re.compile(
        r"(?P<currency>₹|INR|USD|US\$|\$|EUR|€|GBP|£)\s*"
        r"(?P<min>\d[\d,]*(?:\.\d+)?)\s*(?:-|–|to)\s*"
        r"(?P<max>\d[\d,]*(?:\.\d+)?)\s*"
        r"(?P<period>per\s+(?:year|annum|month)|/\s*(?:year|yr|month|mo)|LPA|lakhs?\s+per\s+annum)?",
        flags=re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    currency_raw = match.group("currency").upper()
    currency = {
        "₹": "INR",
        "US$": "USD",
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
    }.get(currency_raw, currency_raw)
    period_raw = (match.group("period") or "").casefold()
    period = None
    if period_raw:
        period = "MONTHLY" if "month" in period_raw or "mo" in period_raw else "YEARLY"
    minimum = float(match.group("min").replace(",", ""))
    maximum = float(match.group("max").replace(",", ""))
    if "lpa" in period_raw or "lakh" in period_raw:
        minimum *= 100_000
        maximum *= 100_000
    value = {"min": minimum, "max": maximum, "currency": currency, "period": period}
    evidence.append(_evidence("salary", value, match, "salary:explicit-range", text))
    return value
