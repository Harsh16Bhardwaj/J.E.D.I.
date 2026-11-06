"""Transition policy shared by application records and private drafts."""

from fastapi import HTTPException

from backend.schemas.product import ApplicationStatus

TERMINAL_APPLICATION_STATES = {
    ApplicationStatus.ACCEPTED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
}
APPLICATION_STAGE_ORDER = {
    stage: index for index, stage in enumerate(ApplicationStatus)
}


def validate_application_move(
    previous: str,
    target: ApplicationStatus,
    *,
    correction: bool,
    notes: str | None,
) -> None:
    if previous == target:
        raise HTTPException(409, "This application is already in that stage.")
    backwards = (
        previous in TERMINAL_APPLICATION_STATES
        or APPLICATION_STAGE_ORDER[target] < APPLICATION_STAGE_ORDER[previous]
    )
    if backwards and not correction:
        raise HTTPException(409, "Record a correction to reopen or move backwards.")
    if correction and not notes:
        raise HTTPException(422, "Add a reason for the correction.")
