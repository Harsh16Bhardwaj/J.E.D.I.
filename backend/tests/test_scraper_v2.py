import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from backend.services import scraper
from backend.services.scraper import (
    SourceSpec,
    assess_candidate,
    discover_company_sources,
    fetch_source_jobs,
    load_scraper_config,
    source_from_url,
    source_identity_consistent,
)
from backend.services.scraper_enrichment import extract_facts


def candidate(*, days: int, evidence: str, location: str = "Remote - India") -> dict:
    return {
        "roleTitle": "Backend Engineer",
        "location": location,
        "description": (
            "Build Python APIs using PostgreSQL and AWS. "
            "Requirements and responsibilities. "
        )
        * 6,
        "postedAt": (datetime.now(UTC) - timedelta(days=days)).isoformat(),
        "applyUrl": "https://careers.example.com/jobs/backend-1",
        "__dateEvidence": evidence,
    }


def test_two_tier_freshness_and_strict_remote_policy() -> None:
    config = load_scraper_config()
    recommended = assess_candidate(
        candidate(days=5, evidence="JSON_LD_DATE_POSTED"), config
    )
    assert recommended.freshness_tier == "VERIFIED_RECENT"
    assert recommended.review_group == "RECOMMENDED"

    review = assess_candidate(candidate(days=20, evidence="ATS_UPDATED_AT"), config)
    assert review.freshness_tier == "REVIEW_RECENT"
    assert review.review_group == "NEEDS_REVIEW"

    owner_review = assess_candidate(
        candidate(
            days=2,
            evidence="JSON_LD_DATE_POSTED",
            location="Remote - United States",
        ),
        config,
    )
    assert owner_review.review_group == "NEEDS_REVIEW"
    assert owner_review.source_quality_valid is True
    assert "NOT_INDIA_ELIGIBLE" in owner_review.quality_failures


def test_taxonomy_records_evidence_and_leaves_conflicts_unknown() -> None:
    result = extract_facts(
        "Use Python, FastAPI, PostgreSQL and AWS. Requires 1-3 years of experience. "
        "This is a full-time role and a bachelor's degree is required."
    )
    assert {"Python", "FastAPI", "PostgreSQL", "AWS"}.issubset(
        set(result.facts["skills"])
    )
    assert result.facts["experienceMinYears"] == 1
    assert result.facts["experienceMaxYears"] == 3
    assert result.evidence
    assert all(
        {"field", "text", "rule", "start", "end"} <= set(item)
        for item in result.evidence
    )

    conflict = extract_facts("Requires 1-2 years. Another section requires 4+ years.")
    assert conflict.facts["experienceMinYears"] is None
    assert conflict.facts["experienceMaxYears"] is None


def test_v2_source_urls_are_detected() -> None:
    recruitee = source_from_url("https://acme.recruitee.com/o/backend", "recruitee")
    personio = source_from_url("https://acme.jobs.personio.de/job/1", "personio")
    workday = source_from_url(
        "https://acme.wd1.myworkdayjobs.com/en-US/External", "workday"
    )
    generic = source_from_url("https://acme.example/careers", "jsonld")
    assert recruitee and recruitee.board_token == "acme"
    assert personio and personio.board_token == "acme"
    assert workday and workday.board_token.startswith("https://")
    assert generic and generic.ats_type == "jsonld"


def test_company_identity_is_not_satisfied_by_the_configured_display_name() -> None:
    wrong = SourceSpec(
        "recruitee:other",
        "Acme Labs",
        "recruitee",
        "other.recruitee.com",
        "other",
    )
    jobs = [{"companyName": "Acme Labs", "applyUrl": "https://other.recruitee.com/o/1"}]
    assert not source_identity_consistent("Acme Labs", wrong, jobs)


def test_recruitee_personio_workday_and_jsonld_adapters(monkeypatch) -> None:
    config = load_scraper_config()
    now = datetime.now(UTC).isoformat()

    async def fake_json(url, _config, *, allow_unlocker=True):
        if "recruitee" in url:
            return {
                "offers": [
                    {
                        "title": "Backend Engineer",
                        "description": "Build Python services. " * 20,
                        "careers_url": "https://acme.recruitee.com/o/backend",
                        "location": "Remote - India",
                        "published_at": now,
                    }
                ]
            }, 0
        return {
            "jobPostingInfo": {
                "jobDescription": "Build reliable Python services. " * 20,
                "startDate": now,
            }
        }, 0

    async def fake_post(_url, _payload, _config):
        return {
            "total": 1,
            "jobPostings": [
                {
                    "title": "Backend Engineer",
                    "locationsText": "Remote - India",
                    "postedOn": now,
                    "externalPath": "/job/India/Backend_JR1",
                }
            ],
        }

    personio_xml = f"""
    <workzag-jobs><position><id>1</id><name>Backend Engineer</name>
    <office>Remote - India</office><createdAt>{now}</createdAt>
    <jobDescriptions><jobDescription>
    {"Build Python APIs. " * 25}
    </jobDescription></jobDescriptions>
    <url>https://acme.jobs.personio.de/job/1</url></position></workzag-jobs>
    """
    jsonld = f"""
    <script type="application/ld+json">
    {{"@type":"JobPosting","title":"Backend Engineer",
    "description":"{"Build Python APIs. " * 25}","datePosted":"{now}",
    "url":"https://acme.example/jobs/1","jobLocation":{{"address":{{"addressCountry":"India"}}}},
    "hiringOrganization":{{"name":"Acme"}}}}</script>
    """

    async def fake_text(url, _config, *, allow_unlocker=True):
        return (personio_xml if "personio" in url else jsonld), 0

    monkeypatch.setattr(scraper, "_get_json", fake_json)
    monkeypatch.setattr(scraper, "_post_json", fake_post)
    monkeypatch.setattr(scraper, "_get_text", fake_text)
    sources = [
        SourceSpec("recruitee:acme", "Acme", "recruitee", "acme.recruitee.com", "acme"),
        SourceSpec(
            "personio:acme", "Acme", "personio", "acme.jobs.personio.de", "acme"
        ),
        SourceSpec(
            "workday:acme",
            "Acme",
            "workday",
            "acme.wd1.myworkdayjobs.com",
            "https://acme.wd1.myworkdayjobs.com/en-US/External",
        ),
        SourceSpec(
            "jsonld:acme",
            "Acme",
            "jsonld",
            "acme.example",
            "https://acme.example/careers",
        ),
    ]
    for source in sources:
        result = asyncio.run(fetch_source_jobs(source, config))
        assert len(result.jobs) == 1
        assert result.jobs[0]["applyUrl"].startswith("https://")


def test_discovery_follows_employer_linked_public_board(monkeypatch) -> None:
    async def fake_text(_url, _config, *, allow_unlocker=True):
        return '<a href="https://acme.recruitee.com/o/backend">Careers</a>', 0

    monkeypatch.setattr(scraper, "_get_text", fake_text)
    result = asyncio.run(
        discover_company_sources("Acme", "acme.example", load_scraper_config())
    )
    assert [item["source_key"] for item in result.jobs] == ["recruitee:acme"]
    assert result.free_requests >= 1


def test_unlocker_is_used_only_for_missing_shortlisted_detail(monkeypatch) -> None:
    config = load_scraper_config()
    now = datetime.now(UTC).isoformat()

    async def listing(_url, _config, *, etag, last_modified):
        return (
            {
                "jobs": [
                    {
                        "title": "Backend Engineer",
                        "content": "Build Python APIs. " * 20,
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                        "location": {"name": "Remote - India"},
                    }
                ]
            },
            0,
            None,
            None,
            False,
        )

    async def direct_page(_url, _config, *, allow_unlocker=True):
        return "<html>missing structured facts</html>", 0

    async def unlocker(_url, *, zone, data_format="json"):
        assert zone == "unlocker-zone"
        return f"""
        <script type="application/ld+json">
        {{"@type":"JobPosting","title":"Backend Engineer",
        "description":"{"Build Python APIs. " * 20}","datePosted":"{now}",
        "url":"https://boards.greenhouse.io/acme/jobs/1"}}
        </script>
        """

    monkeypatch.setattr(scraper, "_get_json_conditional", listing)
    monkeypatch.setattr(scraper, "_get_text", direct_page)
    monkeypatch.setattr(scraper, "_bright_data_request", unlocker)
    monkeypatch.setattr(
        scraper,
        "get_settings",
        lambda: SimpleNamespace(
            bright_data_api_key="key", bright_data_unlocker_zone="unlocker-zone"
        ),
    )
    source = SourceSpec(
        "greenhouse:acme",
        "Acme",
        "greenhouse",
        "boards.greenhouse.io",
        "acme",
    )
    result = asyncio.run(fetch_source_jobs(source, config))
    assert result.bright_data_used == 1
    assert result.jobs[0]["__dateEvidence"] == "JSON_LD_DATE_POSTED"
    assert result.provider_uses == (
        {
            "candidateUrl": "https://boards.greenhouse.io/acme/jobs/1",
            "provider": "brightdata-unlocker",
            "units": 1,
            "reason": "Shortlisted vacancy detail was blocked or incomplete",
        },
    )


def test_smartrecruiters_page_checkpoint_resumes_without_restarting(
    monkeypatch,
) -> None:
    calls: list[int] = []

    async def fake_json(url, _config, *, allow_unlocker=True):
        offset = int(url.split("offset=")[-1])
        calls.append(offset)
        count = 100 if offset == 0 else 50
        return {
            "totalFound": 150,
            "content": [
                {
                    "id": f"{offset + index}",
                    "name": "Sales Representative",
                    "ref": f"https://jobs.smartrecruiters.com/acme/{offset + index}",
                    "company": {"name": "Acme"},
                    "location": {"fullLocation": "India"},
                }
                for index in range(count)
            ],
        }, 0

    monkeypatch.setattr(scraper, "_get_json", fake_json)
    source = SourceSpec(
        "smartrecruiters:acme",
        "Acme",
        "smartrecruiters",
        "jobs.smartrecruiters.com",
        "acme",
    )
    first = asyncio.run(fetch_source_jobs(source, load_scraper_config()))
    second = asyncio.run(
        fetch_source_jobs(
            source, load_scraper_config(), checkpoint=first.next_checkpoint
        )
    )
    assert calls == [0, 100]
    assert first.next_checkpoint == {"offset": 100}
    assert second.next_checkpoint is None


def test_greenhouse_304_reuses_cached_jobs(monkeypatch) -> None:
    cached = candidate(days=2, evidence="JSON_LD_DATE_POSTED")

    async def unchanged(_url, _config, *, etag, last_modified):
        assert etag == '"v1"'
        return None, 0, etag, last_modified, True

    monkeypatch.setattr(scraper, "_get_json_conditional", unchanged)
    source = SourceSpec(
        "greenhouse:acme",
        "Acme",
        "greenhouse",
        "boards.greenhouse.io",
        "acme",
    )
    result = asyncio.run(
        fetch_source_jobs(
            source,
            load_scraper_config(),
            etag='"v1"',
            cached_jobs=[cached],
        )
    )
    assert result.jobs == [cached]
    assert result.free_requests == 1
