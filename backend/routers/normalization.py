from types import SimpleNamespace

from fastapi import APIRouter, HTTPException

from backend.auth import CurrentUser
from backend.schemas.modeling import PreparedJobV2
from backend.schemas.product import NormalizeRequest
from backend.services.product import prepare_job

router = APIRouter(prefix="/v1", tags=["normalization"])


@router.post(
    "/normalize",
    response_model=PreparedJobV2,
)
def normalize(body: NormalizeRequest, _user: CurrentUser) -> PreparedJobV2:
    """Expose the same pure transformation used by batch normalization."""
    required_job = {
        "id",
        "code",
        "company_name",
        "company_key",
        "role_title",
        "description",
        "skills",
    }
    required_profile = {
        "resume_text",
        "preferred_titles",
        "preferred_locations",
        "preferred_skills",
    }
    missing_job = required_job - body.job.keys()
    missing_profile = required_profile - body.profile.keys()
    if missing_job or missing_profile:
        raise HTTPException(
            status_code=422,
            detail={
                "missingJobFields": sorted(missing_job),
                "missingProfileFields": sorted(missing_profile),
            },
        )
    job_defaults = {
        "role_family": None,
        "seniority": None,
        "location": None,
        "work_mode": None,
        "employment_type": None,
        "experience_min_years": None,
        "experience_max_years": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "can_apply_now": None,
        "posted_at": None,
    }
    profile_defaults = {
        "experience_min_years": None,
        "experience_max_years": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
    }
    return prepare_job(
        SimpleNamespace(**(job_defaults | body.job)),
        SimpleNamespace(**(profile_defaults | body.profile)),
    )
