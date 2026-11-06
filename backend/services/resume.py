"""Conservative local resume extraction from text, PDF, and DOCX."""

import re
from datetime import date
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile
from zlib import error as ZipCompressionError

from pypdf import PdfReader

from backend.schemas.learning import InferredSkill, ResumeEvidence
from backend.services.skill_vocabulary import BROADER_SKILLS, skill_names, vocabulary

MAX_RESUME_BYTES = 5 * 1024 * 1024
_DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_PACKAGE_TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"
_WORD_NAMESPACES = (
    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}",
    "{http://purl.oclc.org/ooxml/wordprocessingml/main}",
)
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
            "This resume has too little readable text. Upload a text-based file.",
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
    explicit = [
        name
        for name in dict.fromkeys(vocabulary().values())
        if name in positive and name not in negative
    ]
    inferred = []
    for source, target in [
        ("React", "JavaScript"),
        ("Next.js", "React"),
        ("Django", "Python"),
        ("FastAPI", "Python"),
        ("PostgreSQL", "SQL"),
        *BROADER_SKILLS.items(),
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
    if len(data) > MAX_RESUME_BYTES:
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


def _docx_xml(package: ZipFile, path: str, limit: int) -> ElementTree.Element:
    part = package.getinfo(path)
    if part.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
        raise ValueError("Unsupported Word document compression")
    if part.file_size > limit:
        raise ResumeError(
            "DOCX_TOO_LARGE", "Export a simpler Word resume or paste the text."
        )
    with package.open(part) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ResumeError(
            "DOCX_TOO_LARGE", "Export a simpler Word resume or paste the text."
        )
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    xml = data.decode(encoding)
    if "\x00" in xml or "<!DOCTYPE" in xml or "<!ENTITY" in xml:
        raise ResumeError(
            "INVALID_DOCX", "Export a standard DOCX resume and try again."
        )
    return ElementTree.fromstring(xml)


def extract_docx_resume(data: bytes) -> ResumeEvidence:
    if len(data) > MAX_RESUME_BYTES:
        raise ResumeError("DOCX_TOO_LARGE", "Upload a DOCX of 5 MB or less.")
    try:
        with ZipFile(BytesIO(data)) as package:
            names = package.namelist()
            if len(names) > 2_000 or len(names) != len(set(names)):
                raise ValueError("Invalid ZIP directory")
            types = _docx_xml(package, "[Content_Types].xml", 64_000)
            if types.tag != _PACKAGE_TYPES + "Types" or not any(
                entry.tag == _PACKAGE_TYPES + "Override"
                and entry.get("PartName") == "/word/document.xml"
                and entry.get("ContentType") == _DOCX_CONTENT_TYPE
                for entry in types
            ):
                raise ValueError("Missing standard Word document content type")
            document = _docx_xml(package, "word/document.xml", 2_000_000)
        namespace = next(
            (ns for ns in _WORD_NAMESPACES if document.tag == ns + "document"), ""
        )
        body = document.find(namespace + "body") if namespace else None
        if body is None:
            raise ValueError("Missing Word document body")
        separators = {
            namespace + "tab": " ",
            namespace + "br": "\n",
            namespace + "cr": "\n",
        }
        lines = [
            "".join(
                (node.text or "")
                if node.tag == namespace + "t"
                else separators.get(node.tag, "")
                for node in paragraph.iter()
            )
            for paragraph in body.iter(namespace + "p")
        ]
        return parse_resume_text("\n".join(lines))
    except ResumeError as exc:
        if exc.code == "PDF_TOO_LARGE":
            raise ResumeError("DOCX_TOO_LARGE", str(exc)) from exc
        raise
    except (
        BadZipFile,
        ElementTree.ParseError,
        KeyError,
        ValueError,
        RuntimeError,
        ZipCompressionError,
    ) as exc:
        raise ResumeError(
            "INVALID_DOCX",
            "Cannot read this Word document. Export a standard DOCX or paste the text.",
        ) from exc


def extract_resume_isolated(data: bytes) -> ResumeEvidence:
    """Keep unusually complex documents out of the API process."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    docx = data.startswith(b"PK\x03\x04")
    if len(data) > MAX_RESUME_BYTES:
        if docx:
            raise ResumeError("DOCX_TOO_LARGE", "Upload a DOCX of 5 MB or less.")
        raise ResumeError("PDF_TOO_LARGE", "Upload a PDF of 5 MB or less.")
    if not docx and not data.startswith(b"%PDF-"):
        raise ResumeError("INVALID_PDF", "Upload a valid PDF or DOCX resume.")
    limit_code = "DOCX_PROCESSING_LIMIT" if docx else "PDF_PROCESSING_LIMIT"
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
            limit_code,
            "The document took too long to read. Try a simpler file or paste the text.",
        ) from exc
    if result.returncode != 0:
        raise ResumeError(
            limit_code,
            "The document is too complex. Try a simpler file or paste the text.",
        )
    payload = json.loads(result.stdout)
    if "error" in payload:
        raise ResumeError(payload["error"]["code"], payload["error"]["message"])
    return ResumeEvidence.model_validate(payload)
