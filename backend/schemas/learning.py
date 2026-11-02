"""Resume evidence and version-one theoretical question bank contracts."""

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from backend.schemas.product import ApiModel


class InferredSkill(ApiModel):
    skill: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=1, max_length=1000)


class ResumeEvidence(ApiModel):
    text: str = Field(min_length=1, max_length=100_000)
    summary: str = Field(default="", max_length=5000)
    contact: list[str] = Field(default_factory=list, max_length=30)
    current_location: str | None = Field(default=None, max_length=500)
    explicit_skills: list[str] = Field(default_factory=list, max_length=200)
    inferred_skills: list[InferredSkill] = Field(default_factory=list, max_length=200)
    projects: list[str] = Field(default_factory=list, max_length=100)
    work_history: list[str] = Field(default_factory=list, max_length=100)
    education: list[str] = Field(default_factory=list, max_length=100)
    experience_years: float | None = Field(default=None, ge=0, le=80)
    limitations: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def bounded_strings(self):
        values = (
            self.contact
            + self.explicit_skills
            + self.projects
            + self.work_history
            + self.education
            + self.limitations
        )
        if any(not x.strip() or len(x) > 5000 for x in values):
            raise ValueError(
                "Evidence entries must be nonempty and at most 5000 characters"
            )
        return self


class ContentModel(ApiModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class QuestionOption(ContentModel):
    id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=5000)
    explanation: str = Field(min_length=1, max_length=5000)


class QuestionAnswer(ContentModel):
    correct_option_id: str
    explanation: str = Field(min_length=1, max_length=5000)


class Question(ContentModel):
    id: str = Field(min_length=1, max_length=100)
    difficulty: Literal["easy", "medium", "hard"]
    question: str = Field(min_length=1, max_length=5000)
    options: list[QuestionOption] = Field(min_length=2, max_length=10)
    answer: QuestionAnswer

    @model_validator(mode="after")
    def valid_answer(self):
        ids = [x.id for x in self.options]
        if len(ids) != len(set(ids)) or self.answer.correct_option_id not in ids:
            raise ValueError("Options must have unique IDs and a valid correctOptionId")
        return self


class QuestionBank(ContentModel):
    schema_version: Literal[1]
    topic_id: str = Field(pattern=r"^[a-z0-9-]+$", max_length=100)
    topic_name: str = Field(min_length=1, max_length=200)
    question_count: int = Field(ge=1, le=2000)
    difficulty_distribution: dict[Literal["easy", "medium", "hard"], int]
    questions: list[Question] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def consistent_counts(self):
        actual = {
            level: sum(q.difficulty == level for q in self.questions)
            for level in ("easy", "medium", "hard")
        }
        if (
            self.question_count != len(self.questions)
            or self.difficulty_distribution != actual
        ):
            raise ValueError(
                "questionCount and difficultyDistribution must match questions"
            )
        if len({q.id for q in self.questions}) != self.question_count:
            raise ValueError("Question IDs must be unique")
        return self


class StartAttempt(ApiModel):
    topic_id: str = Field(max_length=100)
    question_count: int = Field(ge=1, le=200)
    duration_seconds: int = Field(ge=30, le=3600)
    job_id: str | None = Field(default=None, max_length=100)


class SubmitAnswer(ApiModel):
    question_id: str = Field(max_length=100)
    option_id: str = Field(max_length=100)


class TutorMessage(ApiModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6000)


class AskTutor(ApiModel):
    question_id: str = Field(min_length=1, max_length=100)
    message: str = Field(
        default="Explain why my answer is right or wrong, with an example.",
        min_length=1,
        max_length=1000,
    )
    history: list[TutorMessage] = Field(default_factory=list, max_length=6)
