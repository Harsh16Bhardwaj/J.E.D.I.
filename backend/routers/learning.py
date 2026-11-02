"""Member-private resume evidence, skill gaps and server-graded learning sprints."""

from datetime import UTC, datetime, timedelta
from random import SystemRandom
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from backend.auth import CurrentUser
from backend.database import LearningAttempt, ResumeEvidenceRecord, get_session, utc_now
from backend.routers.workspace import get_job_or_404
from backend.schemas.learning import ResumeEvidence, StartAttempt, SubmitAnswer
from backend.services.group_access import require_group_context
from backend.services.learning import TOPIC_SKILLS, compare_skills, load_banks
from backend.services.resume import (
    MAX_PDF_BYTES,
    ResumeError,
    extract_resume_isolated,
    parse_resume_text,
)

router = APIRouter(tags=["resume and learning"])
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


def fail(code: str, message: str, status: int = 422):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


async def member_id(session: AsyncSession, user_id: str) -> str:
    return (await require_group_context(session, user_id)).membership.id


async def evidence_for(session: AsyncSession, owner: str) -> ResumeEvidence | None:
    row = await session.scalar(
        select(ResumeEvidenceRecord).where(
            ResumeEvidenceRecord.group_member_id == owner
        )
    )
    return ResumeEvidence.model_validate(row.evidence) if row else None


@router.post("/api/resume/extract", response_model=ResumeEvidence)
async def extract(file: UploadFile, user: CurrentUser, session: DatabaseSession):
    await member_id(session, user.id)
    try:
        data = await file.read(MAX_PDF_BYTES + 1)
        return await run_in_threadpool(extract_resume_isolated, data)
    except ResumeError as exc:
        fail(exc.code, str(exc))
    finally:
        await file.close()


@router.get("/api/resume", response_model=ResumeEvidence | None)
async def get_resume(user: CurrentUser, session: DatabaseSession):
    return await evidence_for(session, await member_id(session, user.id))


@router.put("/api/resume", response_model=ResumeEvidence)
async def save_resume(
    body: ResumeEvidence, user: CurrentUser, session: DatabaseSession
):
    context = await require_group_context(session, user.id, lock=True)
    try:
        parse_resume_text(body.text)
    except ResumeError as exc:
        fail(exc.code, str(exc))
    row = await session.scalar(
        select(ResumeEvidenceRecord).where(
            ResumeEvidenceRecord.group_member_id == context.membership.id
        )
    )
    if row is None:
        row = ResumeEvidenceRecord(
            group_member_id=context.membership.id,
            evidence=body.model_dump(by_alias=True),
        )
        session.add(row)
    else:
        row.evidence = body.model_dump(by_alias=True)
        row.updated_at = utc_now()
    await session.commit()
    return body


@router.get("/api/jobs/{job_id}/skill-gap")
async def skill_gap(job_id: str, user: CurrentUser, session: DatabaseSession):
    owner = await member_id(session, user.id)
    job = await get_job_or_404(session, job_id)
    return {
        "jobId": job.id,
        "jobTitle": job.role_title,
        **compare_skills(
            job.description, job.skills, await evidence_for(session, owner)
        ),
    }


@router.get("/api/learning/topics")
async def topics(user: CurrentUser, session: DatabaseSession):
    await member_id(session, user.id)
    return [
        {
            "topicId": bank.topic_id,
            "topicName": bank.topic_name,
            "questionCount": bank.question_count,
            "difficultyDistribution": bank.difficulty_distribution,
            "skills": TOPIC_SKILLS.get(bank.topic_id, []),
        }
        for bank in load_banks().values()
    ]


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def attempt_for(
    session: AsyncSession, owner: str, attempt_id: str
) -> LearningAttempt:
    row = await session.scalar(
        select(LearningAttempt)
        .where(
            LearningAttempt.id == attempt_id, LearningAttempt.group_member_id == owner
        )
        .with_for_update()
    )
    if row is None:
        fail("ATTEMPT_NOT_FOUND", "Sprint not found.", 404)
    if row.status == "ACTIVE" and aware(row.deadline_at) <= utc_now():
        row.status = "EXPIRED"
        row.finished_at = row.deadline_at
        row.revision += 1
        await session.commit()
    return row


def attempt_response(row: LearningAttempt) -> dict:
    finished = row.status != "ACTIVE"
    questions = []
    correct = 0
    for question in row.snapshot["questions"]:
        choice = row.answers.get(question["id"])
        visible = finished or choice is not None
        correct += choice == question["answer"]["correctOptionId"]
        options = [
            {
                key: value
                for key, value in option.items()
                if visible or key != "explanation"
            }
            for option in question["options"]
        ]
        item = {
            "id": question["id"],
            "difficulty": question["difficulty"],
            "question": question["question"],
            "options": options,
            "selectedOptionId": choice,
        }
        if visible:
            item["answer"] = question["answer"]
        questions.append(item)
    return {
        "id": row.id,
        "topicId": row.topic_id,
        "topicName": row.snapshot["topicName"],
        "jobId": row.job_id,
        "status": row.status,
        "startedAt": aware(row.started_at).isoformat(),
        "deadlineAt": aware(row.deadline_at).isoformat(),
        "serverNow": utc_now().isoformat(),
        "questions": questions,
        "correct": correct,
        "incorrect": len(row.answers) - correct,
        "unanswered": len(questions) - len(row.answers),
    }


@router.post("/api/learning/attempts", status_code=201)
async def start_attempt(
    body: StartAttempt, user: CurrentUser, session: DatabaseSession
):
    owner = await member_id(session, user.id)
    bank = load_banks().get(body.topic_id)
    if bank is None:
        fail("TOPIC_NOT_FOUND", "Question bank is unavailable.", 404)
    if body.question_count > bank.question_count:
        fail(
            "QUESTION_COUNT_UNAVAILABLE", "Choose no more than the available questions."
        )
    if body.job_id:
        await get_job_or_404(session, body.job_id)
    selected = SystemRandom().sample(
        bank.model_dump(by_alias=True)["questions"], body.question_count
    )
    now = utc_now()
    row = LearningAttempt(
        group_member_id=owner,
        topic_id=body.topic_id,
        job_id=body.job_id,
        snapshot={
            "topicName": bank.topic_name,
            "schemaVersion": 1,
            "questions": selected,
        },
        answers={},
        status="ACTIVE",
        started_at=now,
        deadline_at=now + timedelta(seconds=body.duration_seconds),
    )
    session.add(row)
    await session.commit()
    return attempt_response(row)


@router.get("/api/learning/attempts")
async def list_attempts(user: CurrentUser, session: DatabaseSession):
    owner = await member_id(session, user.id)
    rows = (
        await session.scalars(
            select(LearningAttempt)
            .where(LearningAttempt.group_member_id == owner)
            .order_by(LearningAttempt.started_at.desc())
            .limit(50)
        )
    ).all()
    result = []
    for row in rows:
        row = await attempt_for(session, owner, row.id)
        result.append(attempt_response(row))
    return result


@router.get("/api/learning/attempts/{attempt_id}")
async def get_attempt(attempt_id: str, user: CurrentUser, session: DatabaseSession):
    return attempt_response(
        await attempt_for(session, await member_id(session, user.id), attempt_id)
    )


@router.post("/api/learning/attempts/{attempt_id}/answers")
async def submit_answer(
    attempt_id: str, body: SubmitAnswer, user: CurrentUser, session: DatabaseSession
):
    row = await attempt_for(session, await member_id(session, user.id), attempt_id)
    if row.status != "ACTIVE":
        fail(
            "SPRINT_CLOSED",
            "This sprint has ended. Start a new sprint to practise again.",
            409,
        )
    question = next(
        (q for q in row.snapshot["questions"] if q["id"] == body.question_id), None
    )
    if question is None or body.option_id not in [o["id"] for o in question["options"]]:
        fail("INVALID_ANSWER", "Choose an option from this sprint's question.")
    previous = row.answers.get(body.question_id)
    if previous:
        if previous != body.option_id:
            fail("ANSWER_LOCKED", "This answer has already been submitted.", 409)
        return attempt_response(row)
    answers = {**row.answers, body.question_id: body.option_id}
    # The revision guard also prevents lost updates on engines without row locks.
    changed = await session.execute(
        update(LearningAttempt)
        .where(
            LearningAttempt.id == row.id,
            LearningAttempt.revision == row.revision,
            LearningAttempt.status == "ACTIVE",
            LearningAttempt.deadline_at > utc_now(),
        )
        .values(answers=answers, revision=row.revision + 1)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        await session.rollback()
        fail(
            "SPRINT_CHANGED",
            "The sprint changed or expired. Refresh and try again.",
            409,
        )
    await session.commit()
    await session.refresh(row)
    return attempt_response(row)


@router.post("/api/learning/attempts/{attempt_id}/finish")
async def finish_attempt(attempt_id: str, user: CurrentUser, session: DatabaseSession):
    row = await attempt_for(session, await member_id(session, user.id), attempt_id)
    if row.status == "ACTIVE":
        changed = await session.execute(
            update(LearningAttempt)
            .where(
                LearningAttempt.id == row.id, LearningAttempt.revision == row.revision
            )
            .values(status="FINISHED", finished_at=utc_now(), revision=row.revision + 1)
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            await session.rollback()
            fail("SPRINT_CHANGED", "The sprint changed. Refresh and try again.", 409)
        await session.commit()
        await session.refresh(row)
    return attempt_response(row)
