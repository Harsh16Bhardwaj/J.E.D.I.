import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from backend.services import scraper
from backend.services.scraper import (
    SourceSpec,
    bright_data_setting_configured,
    candidate_allowed,
    canonical_candidate_url,
    experience_range,
    fetch_source_jobs,
    geography_eligibility,
    infer_source_from_url,
    load_scraper_config,
    source_from_url,
)


def test_bright_data_placeholders_are_not_treated_as_paid_zones() -> None:
    assert not bright_data_setting_configured("")
    assert not bright_data_setting_configured("...")
    assert not bright_data_setting_configured("null")
    assert bright_data_setting_configured("jedi_serp")


def test_config_restores_balanced_company_registry() -> None:
    config = load_scraper_config()
    assert config.version == "jedi-site-scraper-v2"
    assert config.lookback_days == 14
    assert config.review_lookback_days == 30
    assert config.target_job_count == 60
    assert config.bright_data_limit == 150
    assert len(config.company_hints) == 135
    assert len(config.seed_sources) >= 60
    assert set(config.ats_types) == {
        "greenhouse",
        "lever",
        "ashby",
        "workable",
        "smartrecruiters",
        "recruitee",
        "personio",
        "workday",
        "jsonld",
    }


def test_filters_senior_explicit_over_five_and_stale_roles() -> None:
    config = load_scraper_config()
    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    base = {
        "roleTitle": "Backend Engineer",
        "location": "Remote - India",
        "experienceMinYears": None,
        "postedAt": recent,
        "description": "Build production Python APIs and services. " * 12,
        "applyUrl": "https://jobs.example.test/backend-1",
        "__dateEvidence": "JSON_LD_DATE_POSTED",
    }
    assert candidate_allowed(base, config)
    assert not candidate_allowed(
        {**base, "roleTitle": "Senior Backend Engineer"}, config
    )
    assert not candidate_allowed({**base, "experienceMinYears": 6}, config)
    assert not candidate_allowed(
        {**base, "postedAt": (datetime.now(UTC) - timedelta(days=15)).isoformat()},
        config,
    )
    assert experience_range("Requires 2-4 years of experience") == (2.0, 4.0)
    assert experience_range("Experience helpful but not required") == (None, None)


@pytest.mark.parametrize(
    ("ats_type", "url", "token"),
    [
        ("greenhouse", "https://boards.greenhouse.io/acme/jobs/123", "acme"),
        ("greenhouse", "https://job-boards.greenhouse.io/acme/jobs/123", "acme"),
        ("lever", "https://jobs.lever.co/acme/123", "acme"),
        ("ashby", "https://jobs.ashbyhq.com/acme/123", "acme"),
        ("workable", "https://apply.workable.com/acme/j/123", "acme"),
        ("smartrecruiters", "https://jobs.smartrecruiters.com/acme/123", "acme"),
    ],
)
def test_supported_ats_urls_resolve_to_board_tokens(
    ats_type: str, url: str, token: str
) -> None:
    source = source_from_url(url, ats_type)
    assert source is not None
    assert source.board_token == token
    assert source.source_key == f"{ats_type}:{token}"


def test_manual_source_url_infers_supported_ats_and_rejects_other_boards() -> None:
    source = infer_source_from_url(
        "https://jobs.ashbyhq.com/example-company/role-id", name="Example"
    )
    assert source.source_key == "ashby:example-company"
    assert source.name == "Example"
    with pytest.raises(ValueError, match="Aggregator"):
        infer_source_from_url("https://www.linkedin.com/jobs/view/123")


@pytest.mark.parametrize(
    ("ats_type", "payload", "expected_company"),
    [
        (
            "greenhouse",
            {
                "jobs": [
                    {
                        "title": "Backend Engineer",
                        "content": "<p>Build APIs with 1-3 years experience.</p>",
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                        "location": {"name": "Remote - India"},
                        "updated_at": "2026-08-10T10:00:00Z",
                    }
                ]
            },
            "Acme",
        ),
        (
            "lever",
            [
                {
                    "text": "Software Engineer",
                    "descriptionPlain": "Build software with 2+ years experience.",
                    "hostedUrl": "https://jobs.lever.co/acme/1",
                    "categories": {"location": "India", "commitment": "Full-time"},
                    "createdAt": 1786356000000,
                }
            ],
            "Acme",
        ),
        (
            "ashby",
            {
                "jobs": [
                    {
                        "title": "ML Engineer",
                        "descriptionPlain": "Build ML services.",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                        "location": "Remote",
                        "publishedAt": "2026-08-10T10:00:00Z",
                    }
                ]
            },
            "Acme",
        ),
        (
            "workable",
            {
                "name": "Acme Workable",
                "jobs": [
                    {
                        "title": "Web Developer",
                        "description": "Build web applications.",
                        "url": "https://apply.workable.com/acme/j/1",
                        "location": {"location_str": "Bengaluru"},
                        "created_at": "2026-08-10T10:00:00Z",
                    }
                ],
            },
            "Acme Workable",
        ),
        (
            "smartrecruiters",
            {
                "content": [
                    {
                        "name": "AI Engineer",
                        "jobAd": "Build AI systems.",
                        "ref": "https://jobs.smartrecruiters.com/acme/1",
                        "company": {"name": "Acme Smart"},
                        "location": {"fullLocation": "Remote - India"},
                        "releasedDate": "2026-08-10T10:00:00Z",
                    }
                ]
            },
            "Acme Smart",
        ),
    ],
)
def test_all_five_ats_adapters_map_to_jedi_jobs(
    monkeypatch, ats_type: str, payload: object, expected_company: str
) -> None:
    async def fake_get_json(url, config, *, allow_unlocker=True):
        if ats_type == "smartrecruiters" and "/postings/" in url:
            return {
                "jobAd": {
                    "jobDescription": "Build reliable AI systems. " * 15,
                    "qualifications": "One to three years of experience.",
                },
                "releasedDate": "2026-08-10T10:00:00Z",
                "applyUrl": "https://jobs.smartrecruiters.com/acme/1",
            }, 0
        return payload, 0

    async def fake_get_json_conditional(url, config, *, etag, last_modified):
        return payload, 0, None, None, False

    async def fake_get_text(url, config, *, allow_unlocker=True):
        return "<html></html>", 0

    monkeypatch.setattr(scraper, "_get_json", fake_get_json)
    monkeypatch.setattr(scraper, "_get_json_conditional", fake_get_json_conditional)
    monkeypatch.setattr(scraper, "_get_text", fake_get_text)
    source = SourceSpec(
        source_key=f"{ats_type}:acme",
        name="Acme",
        ats_type=ats_type,
        domain_hint="example.test",
        board_token="acme",
    )
    result = asyncio.run(fetch_source_jobs(source, load_scraper_config()))
    assert result.bright_data_used == 0
    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job["companyName"] == expected_company
    assert job["description"]
    if ats_type == "greenhouse":
        assert job["postedAt"] is None
    else:
        assert job["postedAt"]
    assert canonical_candidate_url(job).startswith("https://")


def test_canonical_url_removes_tracking_and_keeps_job_identity() -> None:
    first = canonical_candidate_url(
        {"applyUrl": "https://jobs.example.com/roles/123?utm_source=google"}
    )
    second = canonical_candidate_url(
        {"applyUrl": "https://jobs.example.com/roles/123?utm_campaign=test"}
    )
    assert first == second


def test_remote_geography_requires_india_or_global_eligibility() -> None:
    config = load_scraper_config()
    assert geography_eligibility("Remote - India", config) == "ELIGIBLE"
    assert geography_eligibility("Worldwide Remote", config) == "ELIGIBLE"
    assert geography_eligibility("Remote - United States", config) == "INELIGIBLE"
    assert geography_eligibility("Remote", config) == "AMBIGUOUS"
