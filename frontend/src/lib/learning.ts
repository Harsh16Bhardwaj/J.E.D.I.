export type InferredSkill = { skill: string; evidence: string };
export type ResumeEvidence = {
  text: string;
  summary: string;
  contact: string[];
  currentLocation: string | null;
  explicitSkills: string[];
  inferredSkills: InferredSkill[];
  projects: string[];
  workHistory: string[];
  education: string[];
  experienceYears: number | null;
  limitations: string[];
};
export type SkillRequirement = {
  skill: string;
  requirement: "required" | "preferred" | "uncertain";
  evidence: string;
};
export type SkillGap = {
  jobId: string;
  jobTitle: string;
  hasResume: boolean;
  matched: (SkillRequirement & { source: "explicit" | "inferred" })[];
  missing: (SkillRequirement & { topicIds: string[] })[];
};
export type LearningTopic = {
  topicId: string;
  topicName: string;
  questionCount: number;
  difficultyDistribution: Record<string, number>;
  skills: string[];
};
export type SprintQuestion = {
  id: string;
  difficulty: string;
  question: string;
  options: { id: string; text: string; explanation?: string }[];
  answer?: { correctOptionId: string; explanation: string };
  selectedOptionId: string | null;
};
export type SprintAttempt = {
  id: string;
  topicId: string;
  topicName: string;
  jobId: string | null;
  status: "ACTIVE" | "FINISHED" | "EXPIRED";
  startedAt: string;
  deadlineAt: string;
  serverNow: string;
  questions: SprintQuestion[];
  correct: number;
  incorrect: number;
  unanswered: number;
};
export function remainingSeconds(
  deadline: string,
  now: number,
  serverOffset: number,
) {
  return Math.max(
    0,
    Math.ceil((Date.parse(deadline) - now - serverOffset) / 1000),
  );
}
export function sprintSettings(
  count: number,
  seconds: number,
  available: number,
) {
  return (
    Number.isInteger(count) &&
    count >= 1 &&
    count <= Math.min(available, 200) &&
    Number.isInteger(seconds) &&
    seconds >= 30 &&
    seconds <= 3600
  );
}
export function nextQuestionIndex(
  questions: { selectedOptionId: string | null }[],
) {
  return Math.max(
    0,
    questions.findIndex((q) => q.selectedOptionId === null),
  );
}
