"""Fetch one public posting through an allowlisted provider API."""

import asyncio
import json
import re
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any, NamedTuple
from urllib.parse import urlsplit

import httpx

from backend.schemas.job_intake import LinkedJobPreview
from backend.services.job_intake import preview_job

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
BOARD = r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}"
POSTING_ID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
GREENHOUSE = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
LEVER = {
    "jobs.lever.co": "api.lever.co",
    "jobs.eu.lever.co": "api.eu.lever.co",
}


class JobLinkError(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code = code
        self.status = status


class JobLink(NamedTuple):
    provider: str
    url: str
    endpoint: str
    posting_id: str


def parse_job_link(value: str) -> JobLink:
    unsupported = JobLinkError(
        "UNSUPPORTED_JOB_URL",
        "Use a Greenhouse, Lever, or Ashby posting link, or paste the description.",
    )
    try:
        parts = urlsplit(value.strip())
    except ValueError as exc:
        raise unsupported from exc
    host = parts.hostname
    if (
        parts.scheme != "https"
        or not host
        or parts.netloc.casefold() != host
        or re.search(r"[\x00-\x20\x7f\\]", value.strip())
    ):
        raise unsupported
    if host in GREENHOUSE:
        match = re.fullmatch(rf"/({BOARD})/jobs/([0-9]{{1,20}})/?", parts.path)
        if match:
            board, posting = match.groups()
            return JobLink(
                "greenhouse",
                f"https://{host}/{board}/jobs/{posting}",
                f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{posting}",
                posting,
            )
    elif host in LEVER:
        match = re.fullmatch(rf"/({BOARD})/({POSTING_ID})(?:/apply)?/?", parts.path)
        if match:
            board, posting = match.groups()
            posting = posting.lower()
            return JobLink(
                "lever",
                f"https://{host}/{board}/{posting}",
                f"https://{LEVER[host]}/v0/postings/{board}/{posting}",
                posting,
            )
    elif host == "jobs.ashbyhq.com":
        match = re.fullmatch(
            rf"/({BOARD})/({POSTING_ID})(?:/application)?/?", parts.path
        )
        if match:
            board, posting = match.groups()
            posting = posting.lower()
            return JobLink(
                "ashby",
                f"https://{host}/{board}/{posting}",
                f"https://api.ashbyhq.com/posting-api/job-board/{board}",
                posting,
            )
    raise unsupported


class PostingText(HTMLParser):
    BLOCKS = {"p", "br", "li", "ul", "ol", "div", "h1", "h2", "h3", "h4", "tr"}
    HIDDEN = {"script", "style", "template"}

    def __init__(self):
        super().__init__()
        self.chunks: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden += 1
        elif tag in self.BLOCKS and not self.hidden:
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self.HIDDEN and self.hidden:
            self.hidden -= 1
        elif tag in self.BLOCKS and not self.hidden:
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.chunks.append(data)


def html_text(value: Any) -> str:
    parser = PostingText()
    parser.feed(unescape(value) if isinstance(value, str) else "")
    parser.close()
    return "\n".join(
        line
        for raw in "".join(parser.chunks).splitlines()
        if (line := " ".join(raw.split()))
    )


def missing_posting() -> JobLinkError:
    return JobLinkError(
        "JOB_POSTING_UNAVAILABLE",
        "This posting may have closed. You can still paste its description.",
        404,
    )


def invalid_payload() -> JobLinkError:
    return JobLinkError(
        "JOB_SOURCE_RESPONSE",
        "The provider returned an unreadable posting. Paste the description instead.",
        502,
    )


async def fetch_provider_data(link: JobLink) -> dict:
    try:
        async with asyncio.timeout(12):
            async with (
                httpx.AsyncClient(
                    timeout=httpx.Timeout(6, connect=4),
                    follow_redirects=False,
                    trust_env=False,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as client,
                client.stream("GET", link.endpoint) as response,
            ):
                if response.status_code in {404, 410}:
                    raise missing_posting()
                if response.status_code == 429:
                    raise JobLinkError(
                        "JOB_SOURCE_RATE_LIMITED",
                        "The provider is rate limiting requests. Try later "
                        "or paste the description.",
                        429,
                    )
                if (
                    response.status_code != 200
                    or response.headers.get("content-encoding", "identity")
                    != "identity"
                ):
                    raise invalid_payload()
                data = bytearray()
                async for chunk in response.aiter_raw():
                    if len(data) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise invalid_payload()
                    data.extend(chunk)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise JobLinkError(
            "JOB_SOURCE_TIMEOUT",
            "The provider took too long. Paste the description to continue.",
            504,
        ) from exc
    except httpx.RequestError as exc:
        raise invalid_payload() from exc
    try:
        payload = json.loads(data)
    except (ValueError, RecursionError) as exc:
        raise invalid_payload() from exc
    if not isinstance(payload, dict):
        raise invalid_payload()
    return payload


def posting_text(link: JobLink, payload: dict) -> tuple[dict, str]:
    if link.provider == "greenhouse":
        if str(payload.get("id")) != link.posting_id or (
            "internal_job_id" in payload and payload["internal_job_id"] is None
        ):
            raise missing_posting()
        deadline = payload.get("application_deadline")
        if isinstance(deadline, str):
            try:
                closes_at = datetime.fromisoformat(deadline)
            except ValueError:
                closes_at = None
            if closes_at and (
                closes_at if closes_at.tzinfo else closes_at.replace(tzinfo=UTC)
            ) < datetime.now(UTC):
                raise missing_posting()
        location = payload.get("location")
        return {
            "Job title": payload.get("title"),
            "Employer": payload.get("company_name"),
            "Location": location.get("name") if isinstance(location, dict) else None,
        }, html_text(payload.get("content"))
    if link.provider == "lever":
        if str(payload.get("id", "")).lower() != link.posting_id:
            raise missing_posting()
        categories = payload.get("categories")
        categories = categories if isinstance(categories, dict) else {}
        plain = payload.get("descriptionPlain")
        sections = [
            plain if isinstance(plain, str) else html_text(payload.get("description"))
        ]
        lists = payload.get("lists")
        if isinstance(lists, list):
            for item in lists:
                if not isinstance(item, dict):
                    continue
                heading = " ".join(html_text(item.get("text")).split()).rstrip(":")
                contents = html_text(item.get("content"))
                if contents:
                    sections.append(f"{heading}:\n{contents}" if heading else contents)
        return {
            "Job title": payload.get("text"),
            "Location": categories.get("location"),
            "Employment type": categories.get("commitment"),
            "Work mode": payload.get("workplaceType"),
        }, "\n\n".join(sections)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise invalid_payload()
    for job in jobs:
        if not isinstance(job, dict) or job.get("isListed") is False:
            continue
        url = job.get("jobUrl")
        if not isinstance(url, str):
            continue
        try:
            matches = parse_job_link(url).url == link.url
        except JobLinkError:
            continue
        if matches:
            plain = job.get("descriptionPlain")
            mode = job.get("workplaceType") or (
                "Remote" if job.get("isRemote") is True else None
            )
            return {
                "Job title": job.get("title"),
                "Location": job.get("location"),
                "Employment type": job.get("employmentType"),
                "Work mode": mode,
            }, plain if isinstance(plain, str) else html_text(
                job.get("descriptionHtml")
            )
    raise missing_posting()


async def preview_link(value: str) -> LinkedJobPreview:
    link = parse_job_link(value)
    metadata, body = posting_text(link, await fetch_provider_data(link))
    if len(body.strip()) < 20:
        raise invalid_payload()
    header = [
        f"{label}: {' '.join(value.split())[:300]}"
        for label, value in metadata.items()
        if isinstance(value, str)
        and value.strip()
        and value.casefold() != "unspecified"
    ]
    text = "\n".join(header) + "\n\n" + body.strip()
    description = text[:20_000].strip()
    preview = preview_job(description)
    if len(text) > 20_000:
        preview.warnings.append(
            "Only the first 20,000 characters are shown. "
            "Check the original posting for omitted details."
        )
    return LinkedJobPreview(
        **preview.model_dump(exclude={"source_url"}),
        source_url=link.url,
        description=description,
    )
