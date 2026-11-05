# ruff: noqa: F401, F811

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from backend.services import job_links
from backend.tests.test_product_api import login, product_client

ID = "9f2af478-e919-413d-87c6-59bde6f503c8"
GREENHOUSE = "https://job-boards.greenhouse.io/example/jobs/123"
ASHBY = f"https://jobs.ashbyhq.com/example/{ID}"
LEVER = f"https://jobs.eu.lever.co/example/{ID}"
DESCRIPTION = "Requirements:\nReact.js and three years of software experience."


@pytest.mark.parametrize(
    "url",
    [
        "http://job-boards.greenhouse.io/example/jobs/123",
        "https://job-boards.greenhouse.io.evil.test/example/jobs/123",
        "https://job-boards.greenhouse.io@127.0.0.1/example/jobs/123",
        "https://job-boards.greenhouse.io:8443/example/jobs/123",
        "https://job-boards.greenhouse.io/example%2Fjobs/123",
        "https://127.0.0.1/example/jobs/123",
        "https://[::1]/example/jobs/123",
        "https://job-boards.greenhouse.io/example",
    ],
)
def test_invalid_job_links_never_create_a_fetch_target(url):
    with pytest.raises(job_links.JobLinkError) as error:
        job_links.parse_job_link(url)
    assert error.value.code == "UNSUPPORTED_JOB_URL"


def provider_client(monkeypatch, handler):
    client_class = httpx.AsyncClient

    def client(**options):
        assert options["follow_redirects"] is False
        assert options["trust_env"] is False
        return client_class(transport=httpx.MockTransport(handler), **options)

    monkeypatch.setattr(job_links.httpx, "AsyncClient", client)


def streamed_json(payload):
    return httpx.Response(200, stream=httpx.ByteStream(json.dumps(payload).encode()))


def test_greenhouse_url_preview_and_private_save(product_client, monkeypatch):
    requests = []

    def handle(request):
        requests.append(str(request.url))
        return streamed_json(
            {
                "id": 123,
                "title": "Frontend Engineer",
                "company_name": "Example Labs",
                "location": {"name": "Bengaluru"},
                "content": (
                    "&lt;h2&gt;Requirements&lt;/h2&gt;"
                    "&lt;li&gt;3+ years of Python or Java&lt;/li&gt;"
                    "&lt;script&gt;Docker&lt;/script&gt;"
                ),
            }
        )

    provider_client(monkeypatch, handle)
    base = "/api/job-drafts"
    url = GREENHOUSE + "?token=discard-me#tracking"
    assert (
        product_client.post(f"{base}/preview-url", json={"url": url}).status_code == 401
    )
    login(product_client)
    response = product_client.post(f"{base}/preview-url", json={"url": url})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert requests == ["https://boards-api.greenhouse.io/v1/boards/example/jobs/123"]
    assert preview["sourceUrl"] == GREENHOUSE
    assert preview["fields"]["employer"] == "Example Labs"
    assert preview["fields"]["location"] == "Bengaluru"
    assert "Docker" not in preview["description"]
    assert preview["requirements"][0]["skills"] == ["Python", "Java"]
    assert preview["requirements"][0]["experienceMinYears"] == 3
    path = f"{base}/{uuid4()}"
    saved = product_client.put(path, json={**preview, "revision": 0})
    assert saved.status_code == 200, saved.text
    assert product_client.get(path).json()["sourceUrl"] == GREENHOUSE
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("link", "endpoint", "payload"),
    [
        (
            LEVER + "/apply",
            f"https://api.eu.lever.co/v0/postings/example/{ID}",
            {
                "id": ID,
                "text": "Frontend Engineer",
                "descriptionPlain": "Build accessible browser experiences.",
                "categories": {"commitment": "Full-time"},
                "lists": [{"text": "Requirements", "content": "<li>ReactJS</li>"}],
            },
        ),
        (
            ASHBY + "/application",
            "https://api.ashbyhq.com/posting-api/job-board/example",
            {
                "jobs": [
                    {
                        "jobUrl": ASHBY.replace("/example/", "/another/"),
                        "title": "Other",
                    },
                    {
                        "jobUrl": ASHBY,
                        "title": "Frontend Engineer",
                        "descriptionPlain": DESCRIPTION,
                    },
                ]
            },
        ),
    ],
)
def test_lever_and_ashby_use_exact_posting(monkeypatch, link, endpoint, payload):
    def handle(request):
        assert str(request.url) == endpoint
        return streamed_json(payload)

    provider_client(monkeypatch, handle)
    preview = asyncio.run(job_links.preview_link(link))
    assert preview.fields.title == "Frontend Engineer"
    assert preview.fields.required_skills == ["React"]


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (
            lambda: httpx.Response(302, headers={"Location": "http://127.0.0.1"}),
            "JOB_SOURCE_RESPONSE",
        ),
        (lambda: httpx.Response(429), "JOB_SOURCE_RATE_LIMITED"),
        (lambda: httpx.Response(404), "JOB_POSTING_UNAVAILABLE"),
        (lambda: streamed_json({"padding": "x" * 60}), "JOB_SOURCE_RESPONSE"),
        (lambda: streamed_json({"id": 999}), "JOB_POSTING_UNAVAILABLE"),
    ],
)
def test_provider_failures_are_bounded_and_actionable(monkeypatch, response, code):
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return response()

    monkeypatch.setattr(job_links, "MAX_RESPONSE_BYTES", 50)
    provider_client(monkeypatch, handle)
    with pytest.raises(job_links.JobLinkError) as error:
        asyncio.run(job_links.preview_link(GREENHOUSE))
    assert error.value.code == code
    assert len(calls) == 1
