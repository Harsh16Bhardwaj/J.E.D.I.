"""SQLAlchemy runtime mapping for the tables owned by Prisma migrations."""

import asyncio
import sys
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.config import get_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def new_id() -> str:
    """Create an opaque string id when SQLAlchemy, rather than Prisma, inserts."""
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(UTC)


json_type = JSONB().with_variant(JSON(), "sqlite")
string_list_type = ARRAY(String()).with_variant(JSON(), "sqlite")
batch_status_type = Enum(
    "READY",
    "NORMALIZING",
    "NORMALIZED",
    "RANK_PENDING",
    "RANKING",
    "RANKED",
    "FAILED",
    name="BatchStatus",
).with_variant(String(), "sqlite")
salary_period_type = Enum(
    "YEARLY", "MONTHLY", name="SalaryPeriod"
).with_variant(String(), "sqlite")
relevance_label_type = Enum(
    "DREAM",
    "STRONG_APPLY",
    "CONSIDER",
    "REJECT",
    name="RelevanceLabel",
).with_variant(String(), "sqlite")
review_status_type = Enum(
    "NEW", "VIEWED", "SAVED", "DISMISSED", name="ReviewStatus"
).with_variant(String(), "sqlite")
application_status_type = Enum(
    "NOT_STARTED",
    "PREPARING",
    "APPLIED",
    "SCREENING",
    "ASSESSMENT",
    "INTERVIEW",
    "OFFER",
    "ACCEPTED",
    "REJECTED",
    "WITHDRAWN",
    name="ApplicationStatus",
).with_variant(String(), "sqlite")
application_milestone_type = Enum(
    "SCREENING",
    "ASSESSMENT",
    "INTERVIEW",
    "FOLLOW_UP",
    "OTHER",
    name="ApplicationMilestoneType",
).with_variant(String(), "sqlite")
application_milestone_status_type = Enum(
    "PLANNED",
    "COMPLETED",
    "CANCELLED",
    name="ApplicationMilestoneStatus",
).with_variant(String(), "sqlite")
processing_status_type = Enum(
    "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", name="ProcessingStatus"
).with_variant(String(), "sqlite")
email_status_type = Enum(
    "UNTOUCHED", "SENDING", "SENT", "FAILED", "BLOCKED", "CANCELLED", name="EmailStatus"
).with_variant(String(), "sqlite")
email_campaign_status_type = Enum(
    "WAITING_FOR_RANKINGS",
    "PENDING",
    "SENDING",
    "SENT",
    "PARTIAL_FAILED",
    "FAILED",
    "SKIPPED",
    "EXPIRED",
    name="EmailCampaignStatus",
).with_variant(String(), "sqlite")


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "User"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column("passwordHash", String)
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class Group(Base):
    """One shared v1 workspace with a single ranking profile and model."""

    __tablename__ = "Group"
    __table_args__ = (
        Index("Group_activeProfileVersionId_idx", "activeProfileVersionId"),
        Index("Group_activeModelVersionId_idx", "activeModelVersionId"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, default="JEDI")
    owner_id: Mapped[str] = mapped_column(
        "ownerId", ForeignKey("User.id", ondelete="RESTRICT"), unique=True
    )
    active_profile_version_id: Mapped[str | None] = mapped_column(
        "activeProfileVersionId",
        ForeignKey("ProfileVersion.id", ondelete="SET NULL"),
        nullable=True,
    )
    active_model_version_id: Mapped[str | None] = mapped_column(
        "activeModelVersionId",
        ForeignKey("ModelVersion.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class GroupMember(Base):
    """Connect one user to the only group they can join in v1."""

    __tablename__ = "GroupMember"
    __table_args__ = (
        UniqueConstraint("groupId", "userId", name="GroupMember_groupId_userId_key"),
        Index("GroupMember_groupId_joinedAt_idx", "groupId", "joinedAt"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(
        "groupId", ForeignKey("Group.id", ondelete="CASCADE")
    )
    user_id: Mapped[str] = mapped_column(
        "userId", ForeignKey("User.id", ondelete="CASCADE"), unique=True
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        "onboardingCompletedAt", DateTime(timezone=True), nullable=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        "joinedAt", DateTime(timezone=True), default=utc_now
    )


class GroupInvitation(Base):
    """Reusable short invitation whose plaintext code is never persisted."""

    __tablename__ = "GroupInvitation"
    __table_args__ = (
        Index(
            "GroupInvitation_groupId_revokedAt_expiresAt_idx",
            "groupId",
            "revokedAt",
            "expiresAt",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(
        "groupId", ForeignKey("Group.id", ondelete="CASCADE")
    )
    code_hash: Mapped[str] = mapped_column("codeHash", String, unique=True)
    expires_at: Mapped[datetime] = mapped_column("expiresAt", DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        "revokedAt", DateTime(timezone=True), nullable=True
    )
    usage_count: Mapped[int] = mapped_column("usageCount", Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )


class MemberProfile(Base):
    """A member's stored preferences, intentionally unused by v1 ranking."""

    __tablename__ = "MemberProfile"
    __table_args__ = (Index("MemberProfile_contentHash_idx", "contentHash"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    group_member_id: Mapped[str] = mapped_column(
        "groupMemberId",
        ForeignKey("GroupMember.id", ondelete="CASCADE"),
        unique=True,
    )
    content_hash: Mapped[str] = mapped_column("contentHash", String)
    resume_text: Mapped[str] = mapped_column("resumeText", Text)
    preferred_titles: Mapped[list[str]] = mapped_column(
        "preferredTitles", string_list_type, default=list
    )
    preferred_locations: Mapped[list[str]] = mapped_column(
        "preferredLocations", string_list_type, default=list
    )
    preferred_skills: Mapped[list[str]] = mapped_column(
        "preferredSkills", string_list_type, default=list
    )
    experience_min_years: Mapped[float | None] = mapped_column(
        "experienceMinYears", Float, nullable=True
    )
    experience_max_years: Mapped[float | None] = mapped_column(
        "experienceMaxYears", Float, nullable=True
    )
    salary_min: Mapped[Decimal | None] = mapped_column(
        "salaryMin", Numeric(14, 2), nullable=True
    )
    salary_max: Mapped[Decimal | None] = mapped_column(
        "salaryMax", Numeric(14, 2), nullable=True
    )
    salary_currency: Mapped[str | None] = mapped_column(
        "salaryCurrency", String, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class Batch(Base):
    __tablename__ = "Batch"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    display_name: Mapped[str | None] = mapped_column(
        "displayName", String, unique=True, nullable=True
    )
    external_batch_id: Mapped[str] = mapped_column(
        "externalBatchId", String, unique=True
    )
    content_hash: Mapped[str] = mapped_column("contentHash", String, unique=True)
    schema_version: Mapped[str] = mapped_column("schemaVersion", String)
    prompt_version: Mapped[str | None] = mapped_column(
        "promptVersion", String, nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        "generatedAt", DateTime(timezone=True)
    )
    raw_envelope: Mapped[dict] = mapped_column("rawEnvelope", json_type)
    status: Mapped[str] = mapped_column(batch_status_type, default="READY", index=True)
    received_count: Mapped[int] = mapped_column("receivedCount", Integer, default=0)
    valid_count: Mapped[int] = mapped_column("validCount", Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column("duplicateCount", Integer, default=0)
    job_count: Mapped[int] = mapped_column("jobCount", Integer, default=0)
    validation_report: Mapped[list | None] = mapped_column(
        "validationReport", json_type, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    ranked_at: Mapped[datetime | None] = mapped_column(
        "rankedAt", DateTime(timezone=True), nullable=True
    )


class Job(Base):
    __tablename__ = "Job"
    __table_args__ = (
        Index("Job_companyKey_idx", "companyKey"),
        Index("Job_companyKey_roleTitle_idx", "companyKey", "roleTitle"),
        Index("Job_batchId_idx", "batchId"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String, unique=True)
    dedupe_key: Mapped[str] = mapped_column("dedupeKey", String, unique=True)
    company_key: Mapped[str] = mapped_column("companyKey", String)
    batch_id: Mapped[str] = mapped_column(
        "batchId", ForeignKey("Batch.id", ondelete="CASCADE")
    )
    company_name: Mapped[str] = mapped_column("companyName", String)
    role_title: Mapped[str] = mapped_column("roleTitle", String)
    role_family: Mapped[str | None] = mapped_column("roleFamily", String, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    work_mode: Mapped[str | None] = mapped_column("workMode", String, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(
        "employmentType", String, nullable=True
    )
    description: Mapped[str] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(string_list_type, default=list)
    experience_min_years: Mapped[float | None] = mapped_column(
        "experienceMinYears", Float, nullable=True
    )
    experience_max_years: Mapped[float | None] = mapped_column(
        "experienceMaxYears", Float, nullable=True
    )
    salary_min: Mapped[Decimal | None] = mapped_column(
        "salaryMin", Numeric(14, 2), nullable=True
    )
    salary_max: Mapped[Decimal | None] = mapped_column(
        "salaryMax", Numeric(14, 2), nullable=True
    )
    salary_currency: Mapped[str | None] = mapped_column(
        "salaryCurrency", String, nullable=True
    )
    salary_period: Mapped[str | None] = mapped_column(
        "salaryPeriod", salary_period_type, nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(
        "postedAt", DateTime(timezone=True), nullable=True
    )
    application_deadline: Mapped[datetime | None] = mapped_column(
        "applicationDeadline", DateTime(timezone=True), nullable=True
    )
    can_apply_now: Mapped[bool | None] = mapped_column(
        "canApplyNow", Boolean, nullable=True
    )
    apply_url: Mapped[str] = mapped_column("applyUrl", Text)
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ProfileVersion(Base):
    __tablename__ = "ProfileVersion"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    content_hash: Mapped[str] = mapped_column("contentHash", String, unique=True)
    resume_text: Mapped[str] = mapped_column("resumeText", Text)
    preferred_titles: Mapped[list[str]] = mapped_column(
        "preferredTitles", string_list_type, default=list
    )
    preferred_locations: Mapped[list[str]] = mapped_column(
        "preferredLocations", string_list_type, default=list
    )
    preferred_skills: Mapped[list[str]] = mapped_column(
        "preferredSkills", string_list_type, default=list
    )
    experience_min_years: Mapped[float | None] = mapped_column(
        "experienceMinYears", Float, nullable=True
    )
    experience_max_years: Mapped[float | None] = mapped_column(
        "experienceMaxYears", Float, nullable=True
    )
    salary_min: Mapped[Decimal | None] = mapped_column(
        "salaryMin", Numeric(14, 2), nullable=True
    )
    salary_max: Mapped[Decimal | None] = mapped_column(
        "salaryMax", Numeric(14, 2), nullable=True
    )
    salary_currency: Mapped[str | None] = mapped_column(
        "salaryCurrency", String, nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )


class PreparedJob(Base):
    __tablename__ = "PreparedJob"
    __table_args__ = (
        UniqueConstraint(
            "jobId",
            "profileVersionId",
            "featureSchemaVersion",
            name="PreparedJob_jobId_profileVersionId_featureSchemaVersion_key",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    feature_schema_version: Mapped[str] = mapped_column("featureSchemaVersion", String)
    payload_hash: Mapped[str] = mapped_column("payloadHash", String)
    payload: Mapped[dict] = mapped_column(json_type)
    job_id: Mapped[str] = mapped_column(
        "jobId", ForeignKey("Job.id", ondelete="CASCADE")
    )
    profile_version_id: Mapped[str] = mapped_column(
        "profileVersionId", ForeignKey("ProfileVersion.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class JobState(Base):
    __tablename__ = "JobState"
    __table_args__ = (
        Index("JobState_jobId_idx", "jobId"),
        Index(
            "JobState_groupMemberId_reviewStatus_idx",
            "groupMemberId",
            "reviewStatus",
        ),
        Index("JobState_groupMemberId_viewedAt_idx", "groupMemberId", "viewedAt"),
    )

    group_member_id: Mapped[str] = mapped_column(
        "groupMemberId",
        ForeignKey("GroupMember.id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_id: Mapped[str] = mapped_column(
        "jobId", ForeignKey("Job.id", ondelete="CASCADE"), primary_key=True
    )
    relevance_label: Mapped[str | None] = mapped_column(
        "relevanceLabel", relevance_label_type, nullable=True
    )
    review_status: Mapped[str] = mapped_column(
        "reviewStatus", review_status_type, default="NEW"
    )
    viewed_at: Mapped[datetime | None] = mapped_column(
        "viewedAt", DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class Application(Base):
    __tablename__ = "Application"
    __table_args__ = (
        UniqueConstraint(
            "groupMemberId", "jobId", name="Application_groupMemberId_jobId_key"
        ),
        Index("Application_jobId_idx", "jobId"),
        Index(
            "Application_groupMemberId_status_updatedAt_idx",
            "groupMemberId",
            "status",
            "updatedAt",
        ),
        Index(
            "Application_groupMemberId_nextActionDueAt_idx",
            "groupMemberId",
            "nextActionDueAt",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    group_member_id: Mapped[str] = mapped_column(
        "groupMemberId", ForeignKey("GroupMember.id", ondelete="CASCADE")
    )
    job_id: Mapped[str] = mapped_column(
        "jobId", ForeignKey("Job.id", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(application_status_type, default="NOT_STARTED")
    applied_at: Mapped[datetime | None] = mapped_column(
        "appliedAt", DateTime(timezone=True), nullable=True
    )
    target_apply_by: Mapped[datetime | None] = mapped_column(
        "targetApplyBy", DateTime(timezone=True), nullable=True
    )
    next_action: Mapped[str | None] = mapped_column("nextAction", Text, nullable=True)
    next_action_due_at: Mapped[datetime | None] = mapped_column(
        "nextActionDueAt", DateTime(timezone=True), nullable=True
    )
    portal_url: Mapped[str | None] = mapped_column("portalUrl", Text, nullable=True)
    reference_code: Mapped[str | None] = mapped_column(
        "referenceCode", String, nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        "closedAt", DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt", DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ApplicationMilestone(Base):
    __tablename__ = "ApplicationMilestone"
    __table_args__ = (
        Index(
            "ApplicationMilestone_applicationId_scheduledAt_idx",
            "applicationId",
            "scheduledAt",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        "applicationId",
        ForeignKey("Application.id", ondelete="CASCADE"),
    )
    type: Mapped[str] = mapped_column(application_milestone_type)
    title: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(
        application_milestone_status_type, default="PLANNED"
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        "scheduledAt", DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        "completedAt", DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt", DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class JobEvent(Base):
    __tablename__ = "ApplicationEvent"
    __table_args__ = (
        Index("ApplicationEvent_applicationId_eventAt_idx", "applicationId", "eventAt"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(
        "applicationId", ForeignKey("Application.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column("eventType", String)
    previous_status: Mapped[str | None] = mapped_column(
        "previousStatus", application_status_type, nullable=True
    )
    new_status: Mapped[str | None] = mapped_column(
        "newStatus", application_status_type, nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_at: Mapped[datetime] = mapped_column(
        "eventAt", DateTime(timezone=True), default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )


class JobAnnotation(Base):
    __tablename__ = "JobAnnotation"
    __table_args__ = (Index("JobAnnotation_jobId_idx", "jobId"),)

    group_member_id: Mapped[str] = mapped_column(
        "groupMemberId",
        ForeignKey("GroupMember.id", ondelete="CASCADE"),
        primary_key=True,
    )
    job_id: Mapped[str] = mapped_column(
        "jobId", ForeignKey("Job.id", ondelete="CASCADE"), primary_key=True
    )
    apply_label: Mapped[bool | None] = mapped_column(
        "applyLabel", Boolean, nullable=True
    )
    role_title_fit: Mapped[float | None] = mapped_column(
        "roleTitleFit", Float, nullable=True
    )
    role_family_fit: Mapped[float | None] = mapped_column(
        "roleFamilyFit", Float, nullable=True
    )
    seniority_fit: Mapped[float | None] = mapped_column(
        "seniorityFit", Float, nullable=True
    )
    location_fit: Mapped[float | None] = mapped_column(
        "locationFit", Float, nullable=True
    )
    work_mode_fit: Mapped[float | None] = mapped_column(
        "workModeFit", Float, nullable=True
    )
    experience_fit: Mapped[float | None] = mapped_column(
        "experienceFit", Float, nullable=True
    )
    skills_fit: Mapped[float | None] = mapped_column("skillsFit", Float, nullable=True)
    salary_fit: Mapped[float | None] = mapped_column("salaryFit", Float, nullable=True)
    overall_preference: Mapped[float | None] = mapped_column(
        "overallPreference", Float, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class TrainingExample(Base):
    __tablename__ = "TrainingExample"
    __table_args__ = (
        UniqueConstraint(
            "jobId",
            "profileVersionId",
            "featureSchemaVersion",
            name=("TrainingExample_jobId_profileVersionId_featureSchemaVersion_key"),
        ),
        Index(
            "TrainingExample_annotatedByGroupMemberId_idx",
            "annotatedByGroupMemberId",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    feature_schema_version: Mapped[str] = mapped_column("featureSchemaVersion", String)
    payload_hash: Mapped[str] = mapped_column("payloadHash", String)
    feature_payload: Mapped[dict] = mapped_column("featurePayload", json_type)
    apply_label: Mapped[bool] = mapped_column("applyLabel", Boolean)
    role_title_fit: Mapped[float] = mapped_column("roleTitleFit", Float)
    role_family_fit: Mapped[float] = mapped_column("roleFamilyFit", Float)
    seniority_fit: Mapped[float] = mapped_column("seniorityFit", Float)
    location_fit: Mapped[float] = mapped_column("locationFit", Float)
    work_mode_fit: Mapped[float] = mapped_column("workModeFit", Float)
    experience_fit: Mapped[float] = mapped_column("experienceFit", Float)
    skills_fit: Mapped[float] = mapped_column("skillsFit", Float)
    salary_fit: Mapped[float] = mapped_column("salaryFit", Float)
    overall_preference: Mapped[float] = mapped_column("overallPreference", Float)
    job_id: Mapped[str] = mapped_column(
        "jobId", ForeignKey("Job.id", ondelete="RESTRICT")
    )
    batch_id: Mapped[str] = mapped_column(
        "batchId", ForeignKey("Batch.id", ondelete="RESTRICT")
    )
    profile_version_id: Mapped[str] = mapped_column(
        "profileVersionId",
        ForeignKey("ProfileVersion.id", ondelete="RESTRICT"),
    )
    annotated_by_group_member_id: Mapped[str] = mapped_column(
        "annotatedByGroupMemberId",
        ForeignKey("GroupMember.id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ModelVersion(Base):
    __tablename__ = "ModelVersion"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, unique=True)
    content_hash: Mapped[str] = mapped_column(
        "contentHash", String, unique=True, default=new_id
    )
    description: Mapped[str] = mapped_column(Text, default="")
    model_family: Mapped[str] = mapped_column("modelFamily", String, default="legacy")
    artifact_manifest: Mapped[dict] = mapped_column("artifactManifest", json_type)
    feature_schema_version: Mapped[str] = mapped_column("featureSchemaVersion", String)
    request_contract_version: Mapped[str] = mapped_column(
        "requestContractVersion", String, default="jedi-ranking-v1"
    )
    tags: Mapped[list[str]] = mapped_column(string_list_type, default=list)
    training_metadata: Mapped[dict | None] = mapped_column(
        "trainingMetadata", json_type, nullable=True
    )
    evaluation_metadata: Mapped[dict | None] = mapped_column(
        "evaluationMetadata", json_type, nullable=True
    )
    metrics: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )


class ModelDeployment(Base):
    __tablename__ = "ModelDeployment"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    model_version_id: Mapped[str] = mapped_column(
        "modelVersionId",
        ForeignKey("ModelVersion.id", ondelete="CASCADE"),
        unique=True,
    )
    kind: Mapped[str] = mapped_column(String, default="EMBEDDED")
    endpoint_url: Mapped[str | None] = mapped_column("endpointUrl", Text, nullable=True)
    health_url: Mapped[str | None] = mapped_column("healthUrl", Text, nullable=True)
    artifact_location: Mapped[str | None] = mapped_column(
        "artifactLocation", Text, nullable=True
    )
    deployed_revision: Mapped[str | None] = mapped_column(
        "deployedRevision", String, nullable=True
    )
    timeout_seconds: Mapped[int] = mapped_column("timeoutSeconds", Integer, default=120)
    health_verified_at: Mapped[datetime | None] = mapped_column(
        "healthVerifiedAt", DateTime(timezone=True), nullable=True
    )
    last_health_status: Mapped[str | None] = mapped_column(
        "lastHealthStatus", String, nullable=True
    )
    last_health_latency_ms: Mapped[int | None] = mapped_column(
        "lastHealthLatencyMs", Integer, nullable=True
    )
    last_health_error_code: Mapped[str | None] = mapped_column(
        "lastHealthErrorCode", String, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ModelEndpointCheck(Base):
    __tablename__ = "ModelEndpointCheck"
    __table_args__ = (
        Index(
            "ModelEndpointCheck_modelVersionId_checkedAt_idx",
            "modelVersionId",
            "checkedAt",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    model_version_id: Mapped[str] = mapped_column(
        "modelVersionId",
        ForeignKey("ModelVersion.id", ondelete="CASCADE"),
    )
    deployment_id: Mapped[str] = mapped_column(
        "deploymentId",
        ForeignKey("ModelDeployment.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(String)
    latency_ms: Mapped[int | None] = mapped_column("latencyMs", Integer, nullable=True)
    http_status: Mapped[int | None] = mapped_column(
        "httpStatus", Integer, nullable=True
    )
    error_code: Mapped[str | None] = mapped_column("errorCode", String, nullable=True)
    health_url_snapshot: Mapped[str | None] = mapped_column(
        "healthUrlSnapshot", Text, nullable=True
    )
    returned_feature_schema_version: Mapped[str | None] = mapped_column(
        "returnedFeatureSchemaVersion", String, nullable=True
    )
    returned_request_contract_version: Mapped[str | None] = mapped_column(
        "returnedRequestContractVersion", String, nullable=True
    )
    returned_response_contract_version: Mapped[str | None] = mapped_column(
        "returnedResponseContractVersion", String, nullable=True
    )
    returned_artifact_hash: Mapped[str | None] = mapped_column(
        "returnedArtifactHash", String, nullable=True
    )
    cold_start: Mapped[bool | None] = mapped_column("coldStart", Boolean, nullable=True)
    model_load_ms: Mapped[int | None] = mapped_column(
        "modelLoadMs", Integer, nullable=True
    )
    smoke_test_ms: Mapped[int | None] = mapped_column(
        "smokeTestMs", Integer, nullable=True
    )
    checked_at: Mapped[datetime] = mapped_column(
        "checkedAt", DateTime(timezone=True), default=utc_now
    )


class JobPrediction(Base):
    __tablename__ = "JobPrediction"
    __table_args__ = (
        UniqueConstraint(
            "jobId",
            "processingRunId",
            name="JobPrediction_jobId_processingRunId_key",
        ),
        Index("JobPrediction_processingRunId_rank_idx", "processingRunId", "rank"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    rank: Mapped[int] = mapped_column(Integer)
    jedi_preference_score: Mapped[float] = mapped_column("jediPreferenceScore", Float)
    apply_preference_probability: Mapped[float] = mapped_column(
        "applyPreferenceProbability", Float
    )
    component_scores: Mapped[dict | None] = mapped_column(
        "componentScores", json_type, nullable=True
    )
    ranking_score: Mapped[float] = mapped_column("rankingScore", Float, default=0.0)
    ranking_strategy: Mapped[str] = mapped_column(
        "rankingStrategy", String, default="legacy_jedi_v1"
    )
    apply_threshold: Mapped[float | None] = mapped_column(
        "applyThreshold", Float, nullable=True
    )
    model_apply_decision: Mapped[bool | None] = mapped_column(
        "modelApplyDecision", Boolean, nullable=True
    )
    apply_recommendation: Mapped[bool | None] = mapped_column(
        "applyRecommendation", Boolean, nullable=True
    )
    output_schema_version: Mapped[str] = mapped_column(
        "outputSchemaVersion", String, default="legacy-ranking-v1"
    )
    job_id: Mapped[str] = mapped_column(
        "jobId", ForeignKey("Job.id", ondelete="CASCADE")
    )
    batch_id: Mapped[str] = mapped_column(
        "batchId", ForeignKey("Batch.id", ondelete="CASCADE")
    )
    profile_version_id: Mapped[str] = mapped_column(
        "profileVersionId", ForeignKey("ProfileVersion.id")
    )
    model_version_id: Mapped[str] = mapped_column(
        "modelVersionId", ForeignKey("ModelVersion.id")
    )
    processing_run_id: Mapped[str] = mapped_column(
        "processingRunId",
        ForeignKey("ProcessingRun.id", ondelete="CASCADE"),
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )


class ProcessingRun(Base):
    __tablename__ = "ProcessingRun"
    __table_args__ = (
        Index(
            "ProcessingRun_stage_status_nextAttemptAt_leaseExpiresAt_createdAt_idx",
            "stage",
            "status",
            "nextAttemptAt",
            "leaseExpiresAt",
            "createdAt",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(
        "batchId", ForeignKey("Batch.id", ondelete="CASCADE")
    )
    idempotency_key: Mapped[str] = mapped_column("idempotencyKey", String, unique=True)
    status: Mapped[str] = mapped_column(processing_status_type, default="QUEUED")
    stage: Mapped[str] = mapped_column(String)
    phase: Mapped[str] = mapped_column(String, default="QUEUED")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    trigger: Mapped[str] = mapped_column(String, default="USER")
    retry_of_run_id: Mapped[str | None] = mapped_column(
        "retryOfRunId",
        ForeignKey("ProcessingRun.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    profile_version_id: Mapped[str | None] = mapped_column(
        "profileVersionId",
        ForeignKey("ProfileVersion.id", ondelete="RESTRICT"),
        nullable=True,
    )
    model_version_id: Mapped[str | None] = mapped_column(
        "modelVersionId",
        ForeignKey("ModelVersion.id", ondelete="RESTRICT"),
        nullable=True,
    )
    feature_schema_version: Mapped[str | None] = mapped_column(
        "featureSchemaVersion", String, nullable=True
    )
    lease_token: Mapped[str | None] = mapped_column("leaseToken", String, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        "leaseExpiresAt", DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        "nextAttemptAt", DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        "heartbeatAt", DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column("errorCode", String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(
        "errorMessage", Text, nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        "startedAt", DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        "completedAt", DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )


class ModelInvocation(Base):
    __tablename__ = "ModelInvocation"
    __table_args__ = (
        UniqueConstraint(
            "processingRunId",
            "attempt",
            name="ModelInvocation_processingRunId_attempt_key",
        ),
        Index(
            "ModelInvocation_modelVersionId_startedAt_idx",
            "modelVersionId",
            "startedAt",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    processing_run_id: Mapped[str] = mapped_column(
        "processingRunId",
        ForeignKey("ProcessingRun.id", ondelete="CASCADE"),
    )
    model_version_id: Mapped[str] = mapped_column(
        "modelVersionId",
        ForeignKey("ModelVersion.id", ondelete="RESTRICT"),
    )
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    request_contract_version: Mapped[str] = mapped_column(
        "requestContractVersion", String
    )
    response_contract_version: Mapped[str] = mapped_column(
        "responseContractVersion", String
    )
    feature_schema_version: Mapped[str] = mapped_column("featureSchemaVersion", String)
    artifact_hash: Mapped[str] = mapped_column("artifactHash", String)
    input_hash: Mapped[str] = mapped_column("inputHash", String)
    input_count: Mapped[int] = mapped_column("inputCount", Integer)
    output_count: Mapped[int] = mapped_column("outputCount", Integer, default=0)
    raw_response: Mapped[dict | None] = mapped_column(
        "rawResponse", json_type, nullable=True
    )
    cold_start: Mapped[bool | None] = mapped_column("coldStart", Boolean, nullable=True)
    timings_ms: Mapped[dict | None] = mapped_column(
        "timingsMs", json_type, nullable=True
    )
    error_code: Mapped[str | None] = mapped_column("errorCode", String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(
        "errorMessage", Text, nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        "startedAt", DateTime(timezone=True), default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        "completedAt", DateTime(timezone=True), nullable=True
    )


class EmailConfiguration(Base):
    __tablename__ = "EmailConfiguration"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sender_name: Mapped[str] = mapped_column(
        "senderName", String, default="JEDI Daily Dispatch"
    )
    send_after_ranking: Mapped[bool] = mapped_column(
        "sendAfterRanking", Boolean, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class EmailRecipient(Base):
    __tablename__ = "EmailRecipient"
    __table_args__ = (
        Index("EmailRecipient_active_deletedAt_idx", "active", "deletedAt"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    configuration_id: Mapped[str] = mapped_column(
        "configurationId",
        ForeignKey("EmailConfiguration.id", ondelete="RESTRICT"),
        default="default",
    )
    email: Mapped[str] = mapped_column(String)
    email_normalized: Mapped[str] = mapped_column(
        "emailNormalized", String, unique=True
    )
    display_name: Mapped[str | None] = mapped_column(
        "displayName", String, nullable=True
    )
    group_member_id: Mapped[str | None] = mapped_column(
        "groupMemberId",
        ForeignKey("GroupMember.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        "deletedAt", DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class EmailCampaign(Base):
    __tablename__ = "EmailCampaign"
    __table_args__ = (
        UniqueConstraint(
            "campaignDate",
            "digestType",
            name="EmailCampaign_campaignDate_digestType_key",
        ),
        Index("EmailCampaign_status_scheduledAt_idx", "status", "scheduledAt"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    campaign_date: Mapped[date] = mapped_column("campaignDate", Date)
    digest_type: Mapped[str] = mapped_column(
        "digestType", String, default="DAILY_TOP_10"
    )
    status: Mapped[str] = mapped_column(
        email_campaign_status_type, default="WAITING_FOR_RANKINGS"
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        "scheduledAt", DateTime(timezone=True)
    )
    template_version: Mapped[str] = mapped_column(
        "templateVersion", String, default="daily-top-10-v1"
    )
    payload_snapshot: Mapped[dict | None] = mapped_column(
        "payloadSnapshot", json_type, nullable=True
    )
    selected_job_count: Mapped[int] = mapped_column(
        "selectedJobCount", Integer, default=0
    )
    recipient_count: Mapped[int] = mapped_column("recipientCount", Integer, default=0)
    sent_count: Mapped[int] = mapped_column("sentCount", Integer, default=0)
    failed_count: Mapped[int] = mapped_column("failedCount", Integer, default=0)
    cancelled_count: Mapped[int] = mapped_column("cancelledCount", Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(
        "failureReason", String, nullable=True
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        "lastReconciledAt", DateTime(timezone=True), nullable=True
    )
    queued_at: Mapped[datetime | None] = mapped_column(
        "queuedAt", DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        "sentAt", DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        "completedAt", DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class EmailCampaignRun(Base):
    __tablename__ = "EmailCampaignRun"
    __table_args__ = (Index("EmailCampaignRun_processingRunId_idx", "processingRunId"),)

    campaign_id: Mapped[str] = mapped_column(
        "campaignId",
        ForeignKey("EmailCampaign.id", ondelete="CASCADE"),
        primary_key=True,
    )
    processing_run_id: Mapped[str] = mapped_column(
        "processingRunId",
        ForeignKey("ProcessingRun.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        "addedAt", DateTime(timezone=True), default=utc_now
    )


class EmailDelivery(Base):
    __tablename__ = "EmailDelivery"
    __table_args__ = (
        UniqueConstraint(
            "campaignId",
            "recipientId",
            name="EmailDelivery_campaignId_recipientId_key",
        ),
        UniqueConstraint(
            "batchId",
            "rankingRunId",
            "recipientId",
            name="EmailDelivery_batchId_rankingRunId_recipientId_key",
        ),
        UniqueConstraint(
            "batchId",
            "rankingRunId",
            "groupMemberId",
            name="EmailDelivery_batchId_rankingRunId_groupMemberId_key",
        ),
        Index(
            "EmailDelivery_status_nextAttemptAt_createdAt_idx",
            "status",
            "nextAttemptAt",
            "createdAt",
        ),
        Index("EmailDelivery_campaignId_status_idx", "campaignId", "status"),
        Index("EmailDelivery_createdAt_id_idx", "createdAt", "id"),
        Index("EmailDelivery_batchId_createdAt_idx", "batchId", "createdAt"),
        Index("EmailDelivery_recipientId_createdAt_idx", "recipientId", "createdAt"),
        Index(
            "EmailDelivery_groupMemberId_createdAt_idx", "groupMemberId", "createdAt"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    campaign_id: Mapped[str | None] = mapped_column(
        "campaignId",
        ForeignKey("EmailCampaign.id", ondelete="CASCADE"),
        nullable=True,
    )
    recipient_id: Mapped[str | None] = mapped_column(
        "recipientId",
        ForeignKey("EmailRecipient.id", ondelete="RESTRICT"),
        nullable=True,
    )
    batch_id: Mapped[str | None] = mapped_column(
        "batchId", ForeignKey("Batch.id", ondelete="CASCADE"), nullable=True
    )
    recipient: Mapped[str] = mapped_column(String)
    recipient_display_name: Mapped[str | None] = mapped_column(
        "recipientDisplayName", String, nullable=True
    )
    group_member_id: Mapped[str | None] = mapped_column(
        "groupMemberId",
        ForeignKey("GroupMember.id", ondelete="RESTRICT"),
        nullable=True,
    )
    ranking_run_id: Mapped[str | None] = mapped_column(
        "rankingRunId",
        ForeignKey("ProcessingRun.id", ondelete="RESTRICT"),
        nullable=True,
    )
    template_version: Mapped[str] = mapped_column("templateVersion", String)
    message_id: Mapped[str] = mapped_column("messageId", String, unique=True)
    status: Mapped[str] = mapped_column(email_status_type, default="UNTOUCHED")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_cycle: Mapped[int] = mapped_column("retryCycle", Integer, default=0)
    retry_cycle_attempts: Mapped[int] = mapped_column(
        "retryCycleAttempts", Integer, default=0
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        "providerMessageId", String, nullable=True
    )
    payload_snapshot: Mapped[dict | None] = mapped_column(
        "payloadSnapshot", json_type, nullable=True
    )
    profile_content_hash: Mapped[str | None] = mapped_column(
        "profileContentHash", String, nullable=True
    )
    personalized_jobs: Mapped[list[dict] | None] = mapped_column(
        "personalizedJobs", json_type, nullable=True
    )
    last_error: Mapped[str | None] = mapped_column("lastError", Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column("errorCode", String, nullable=True)
    lease_token: Mapped[str | None] = mapped_column("leaseToken", String, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        "leaseExpiresAt", DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        "nextAttemptAt", DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        "sentAt", DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt", DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class EmailDeliveryAttempt(Base):
    __tablename__ = "EmailDeliveryAttempt"
    __table_args__ = (
        UniqueConstraint(
            "emailDeliveryId",
            "retryCycle",
            "attemptNumber",
            name="EmailDeliveryAttempt_emailDeliveryId_retryCycle_attemptNumber_key",
        ),
        Index(
            "EmailDeliveryAttempt_emailDeliveryId_startedAt_idx",
            "emailDeliveryId",
            "startedAt",
        ),
        Index(
            "EmailDeliveryAttempt_requestedByGroupMemberId_startedAt_idx",
            "requestedByGroupMemberId",
            "startedAt",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    email_delivery_id: Mapped[str] = mapped_column(
        "emailDeliveryId",
        ForeignKey("EmailDelivery.id", ondelete="CASCADE"),
    )
    attempt_number: Mapped[int] = mapped_column("attemptNumber", Integer)
    retry_cycle: Mapped[int] = mapped_column("retryCycle", Integer)
    trigger: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    requested_by_group_member_id: Mapped[str | None] = mapped_column(
        "requestedByGroupMemberId",
        ForeignKey("GroupMember.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        "startedAt", DateTime(timezone=True), default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        "completedAt", DateTime(timezone=True), nullable=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        "providerMessageId", String, nullable=True
    )
    error_code: Mapped[str | None] = mapped_column("errorCode", String, nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(
        "safeErrorMessage", Text, nullable=True
    )


settings = get_settings()
engine = create_async_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=0,
    pool_timeout=10,
    pool_recycle=300,
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
