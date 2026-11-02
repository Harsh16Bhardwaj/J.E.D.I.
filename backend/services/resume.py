"""Conservative local PDF extraction. Document content is data, never instructions."""

import re
from datetime import date
from io import BytesIO

from pypdf import PdfReader

from backend.schemas.learning import InferredSkill, ResumeEvidence

MAX_PDF_BYTES = 5 * 1024 * 1024
SKILLS = {
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
    "Machine Learning": ["machine learning", "scikit-learn", "pytorch"],
    "System Design": ["system design"],
    "Data Structures": ["data structures"],
}
SECTIONS = {
    "summary": ["summary", "profile", "professional summary", "objective", "about me"],
    "skills": [
        "skills",
        "technical skills",
        "technologies",
        "core competencies",
        "technical expertise",
    ],
    "work": [
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "internships",
    ],
    "projects": [
        "projects",
        "personal projects",
        "selected projects",
        "academic projects",
    ],
    "education": ["education", "academic background", "qualifications"],
    "other": [
        "certifications",
        "awards",
        "achievements",
        "publications",
        "interests",
        "languages",
        "references",
    ],
}


class ResumeError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def skill_names(text: str) -> list[str]:
    return [
        name
        for name, aliases in SKILLS.items()
        if any(
            re.search(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", text, re.I)
            for alias in aliases
        )
    ]


def canonical_skill(value: str) -> str:
    for name, aliases in SKILLS.items():
        if value.strip().casefold() in [name.casefold(), *aliases]:
            return name
    return value.strip()


def sections_of(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {key: [] for key in ["header", *SECTIONS]}
    current = "header"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        heading = re.sub(r"^[\W\d_]+", "", line).strip().rstrip(":").casefold()
        section = next(
            (key for key, aliases in SECTIONS.items() if heading in aliases), None
        )
        if section:
            current = section
        else:
            result[current].append(line[:5000])
    return result


_MONTHS = {
    name: index
    for index, name in enumerate(
        [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ],
        1,
    )
}
_DATE = r"(?:[A-Za-z]{3,9}\s+\d{4}|\d{1,2}/\d{4})"
_RANGE = re.compile(rf"({_DATE})\s*[-–—]\s*({_DATE}|present|current|now)", re.I)


def month_index(value: str, today: date) -> int:
    if value.lower() in ("present", "current", "now"):
        return today.year * 12 + today.month - 1
    if "/" in value:
        month, year = map(int, value.split("/"))
    else:
        month_name, year_text = value.split()
        month, year = _MONTHS[month_name[:3].lower()], int(year_text)
    if not 1 <= month <= 12 or not 1940 <= year <= today.year:
        raise ValueError("Uncertain date")
    return year * 12 + month - 1


def work_months(text: str, today: date | None = None) -> int | None:
    today = today or date.today()
    # Mixed precision cannot yield a trustworthy total: never silently omit
    # year-only work periods while presenting the remainder as full experience.
    residual = _RANGE.sub("", text)
    if re.search(r"\b\d{4}\s*[-–—]\s*(?:\d{4}|present|current|now)\b", residual, re.I):
        return None
    intervals = []
    for start, end in _RANGE.findall(text):
        try:
            lower, upper = month_index(start, today), month_index(end, today)
        except (ValueError, KeyError):
            return None
        if lower <= upper <= today.year * 12 + today.month - 1:
            intervals.append((lower, upper + 1))
        else:
            return None
    if not intervals:
        return None
    total, end = 0, 0
    for lower, upper in sorted(intervals):
        total += max(0, upper - max(lower, end))
        end = max(end, upper)
    return total if total <= 80 * 12 else None


def parse_resume_text(text: str) -> ResumeEvidence:
    text = text.replace("\x00", "").strip()
    if len(text) < 80:
        raise ResumeError(
            "UNREADABLE_RESUME",
            "This PDF has too little readable text. Upload a text-based resume.",
        )
    if len(text) > 100_000:
        raise ResumeError("PDF_TOO_LARGE", "Resume text exceeds the supported length.")
    parts = sections_of(text)
    contact = list(
        dict.fromkeys(
            re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|https?://[^\s]+", text)
        )
    )[:30]
    phones = re.findall(r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)", text)
    contact.extend(
        phone.strip() for phone in phones if 10 <= len(re.sub(r"\D", "", phone)) <= 15
    )
    contact = list(dict.fromkeys(contact))[:30]
    # Resume acceptance needs identity/contact plus multiple populated resume sections.
    populated = sum(
        bool(parts[key]) for key in ("work", "education", "projects", "skills")
    )
    if not contact or populated < 2 or not (parts["work"] or parts["education"]):
        raise ResumeError(
            "INVALID_RESUME",
            "This document does not appear to be a resume. Please upload your resume.",
        )
    positive, negative = set(), set()
    for clause in re.split(r"[\n,;]|(?<=[.!?])\s+", text):
        names = skill_names(clause)
        if re.search(
            r"\bno\b.{0,60}\b(?:experience|knowledge|proficiency)\b"
            r"|\b(?:unfamiliar|not familiar|haven't used|have not used|never used)\b",
            clause,
            re.I,
        ):
            negative.update(names)
        else:
            positive.update(names)
    explicit = [name for name in SKILLS if name in positive and name not in negative]
    inferred = []
    for source, target in [
        ("React", "JavaScript"),
        ("Next.js", "React"),
        ("Django", "Python"),
        ("FastAPI", "Python"),
        ("PostgreSQL", "SQL"),
    ]:
        if (
            source in explicit
            and target not in explicit
            and target not in negative
            and target not in {item.skill for item in inferred}
        ):
            inferred.append(
                InferredSkill(
                    skill=target,
                    evidence=(
                        f"Inferred from the explicit mention of {source}; "
                        "confirm your proficiency."
                    ),
                )
            )
    location = re.search(
        r"^(?:location|based in|address)\s*:\s*(.+)$",
        "\n".join(parts["header"]),
        re.I | re.M,
    )
    months = work_months("\n".join(parts["work"]))
    limitations = [
        (
            "Local extraction uses recognized resume section headings "
            "and a finite skill vocabulary. Review all extracted facts."
        ),
        "Inferred skills are tentative evidence, not verified proficiency.",
    ]
    if months is None:
        limitations.append(
            "Work experience could not be calculated reliably; "
            "use month/year date ranges in the work section."
        )
    if not location:
        limitations.append(
            "Current location was not explicitly labeled; please enter it if needed."
        )
    return ResumeEvidence(
        text=text,
        summary="\n".join(parts["summary"])[:5000],
        contact=contact,
        current_location=location.group(1)[:500] if location else None,
        explicit_skills=explicit,
        inferred_skills=inferred,
        projects=parts["projects"][:100],
        work_history=parts["work"][:100],
        education=parts["education"][:100],
        experience_years=round(months / 12, 2) if months is not None else None,
        limitations=limitations,
    )


def extract_resume(data: bytes) -> ResumeEvidence:
    if len(data) > MAX_PDF_BYTES:
        raise ResumeError("PDF_TOO_LARGE", "Upload a PDF of 5 MB or less.")
    if not data.startswith(b"%PDF-"):
        raise ResumeError("INVALID_PDF", "Upload a valid PDF resume.")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ResumeError(
                "ENCRYPTED_PDF",
                "Remove PDF password protection before uploading your resume.",
            )
        if not 1 <= len(reader.pages) <= 10:
            raise ResumeError(
                "PDF_PAGE_LIMIT", "Upload a resume containing 1 to 10 pages."
            )
        chunks = []
        for page in reader.pages:
            # Reject oversized decoded content streams before text layout work.
            content = page.get_contents()
            if content and len(content.get_data()) > 2_000_000:
                raise ResumeError(
                    "PDF_TOO_LARGE",
                    "This PDF is too complex. Export a simpler text-based resume.",
                )
            chunks.append(page.extract_text() or "")
        return parse_resume_text("\n".join(chunks))
    except ResumeError:
        raise
    except Exception as exc:
        raise ResumeError(
            "INVALID_PDF",
            "This PDF could not be read. Export a new PDF resume and try again.",
        ) from exc


def extract_resume_isolated(data: bytes) -> ResumeEvidence:
    """Keep hostile or unusually complex PDF parsing out of the API process."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    if len(data) > MAX_PDF_BYTES:
        raise ResumeError("PDF_TOO_LARGE", "Upload a PDF of 5 MB or less.")
    if not data.startswith(b"%PDF-"):
        raise ResumeError("INVALID_PDF", "Upload a valid PDF resume.")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "backend.services.resume_worker"],
            input=data,
            capture_output=True,
            timeout=15,
            cwd=Path(__file__).resolve().parents[2],
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ResumeError(
            "PDF_PROCESSING_LIMIT",
            "This PDF took too long to read. Export a simpler PDF resume.",
        ) from exc
    if result.returncode != 0:
        raise ResumeError(
            "PDF_PROCESSING_LIMIT",
            "This PDF is too complex to read. Export a simpler PDF resume.",
        )
    payload = json.loads(result.stdout)
    if "error" in payload:
        raise ResumeError(payload["error"]["code"], payload["error"]["message"])
    return ResumeEvidence.model_validate(payload)
