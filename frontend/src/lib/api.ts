export type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
    requestId?: string;
    details?: unknown;
  };
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly requestId?: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type GroupSummary = { id: string; name: string };

export type User = {
  id: string;
  email: string;
  group: GroupSummary | null;
  isGroupOwner: boolean;
  onboardingComplete: boolean;
};

export type Invitation = {
  id: string;
  expiresAt: string;
  revokedAt: string | null;
  usageCount: number;
  createdAt: string;
};

export type CreatedInvitation = Invitation & { code: string };

export type SharedProfile = {
  id: string;
  resumePreview: string;
  preferredTitles: string[];
  preferredLocations: string[];
  preferredSkills: string[];
};

export type SharedModel = {
  id: string;
  name: string;
  featureSchemaVersion: string;
};

export type MemberProfile = {
  id: string;
  contentHash: string;
  resumeText: string;
  preferredTitles: string[];
  preferredLocations: string[];
  preferredSkills: string[];
  experienceMinYears: number | null;
  experienceMaxYears: number | null;
  salaryMin: number | null;
  salaryMax: number | null;
  salaryCurrency: string | null;
  updatedAt: string;
};

export type OnboardingState = {
  group: GroupSummary;
  onboardingComplete: boolean;
  rankingMode: "SHARED_GROUP_PROFILE";
  sharedProfile: SharedProfile | null;
  sharedModel: SharedModel | null;
  memberProfile: MemberProfile | null;
  suggestedTitles: string[];
  suggestedLocations: string[];
  suggestedSkills: string[];
};

export type OnboardingResult = OnboardingState & {
  replayed: boolean;
  initializedSharedProfile: boolean;
  message: string;
};

export type GroupMember = {
  id: string;
  email: string;
  onboardingComplete: boolean;
  joinedAt: string;
  isOwner: boolean;
};

export type GroupSettings = {
  group: GroupSummary;
  isGroupOwner: boolean;
  memberCount: number;
  members: GroupMember[];
  sharedProfile: SharedProfile | null;
  sharedModel: SharedModel | null;
};
export type Health = { service: string; status: string };
export type TimedResult<T> = {
  data: T;
  latencyMs: number;
  checkedAt: string;
};

export type BatchSummary = {
  id: string;
  displayName: string | null;
  externalBatchId: string;
  schemaVersion: string;
  promptVersion: string | null;
  generatedAt: string;
  status: string;
  receivedCount: number;
  validCount: number;
  duplicateCount: number;
  jobCount: number;
  createdAt: string;
  rankedAt: string | null;
};

export type BatchPage = {
  items: BatchSummary[];
  page: number;
  pageSize: number;
  total: number;
};

export type BatchJob = {
  id: string;
  code: string;
  companyName: string;
  roleTitle: string;
  roleFamily: string | null;
  seniority: string | null;
  location: string | null;
  workMode: string | null;
  employmentType: string | null;
  description: string;
  skills: string[];
  experienceMinYears: number | null;
  experienceMaxYears: number | null;
  salaryMin: number | null;
  salaryMax: number | null;
  salaryCurrency: string | null;
  postedAt: string | null;
  applicationDeadline: string | null;
  canApplyNow: boolean | null;
  applyUrl: string;
  annotation: {
    jobId: string;
    relevanceLabel: string | null;
    applyLabel: boolean | null;
    complete: boolean;
  } | null;
};

export type BatchDetail = {
  batch: BatchSummary;
  actions: {
    canDelete: boolean;
    canNormalize: boolean;
    canAnnotate: boolean;
    canAddToTraining: boolean;
    canProcessRanks: boolean;
  };
  preparedCount: number;
  normalizationComplete: boolean;
  manualAnnotationCount: number;
  jobs: BatchJob[];
};

export type BatchCreateResult = {
  batchId: string;
  status: string;
  receivedCount: number;
  validCount: number;
  duplicateCount: number;
  jobCount: number;
  replayed: boolean;
  validationReport: Array<{ sourceIndex: number; errors: unknown[] }>;
};

export type ProfileSummary = {
  id: string;
  active: boolean;
  resumePreview: string;
  preferredTitles: string[];
  preferredLocations: string[];
  preferredSkills: string[];
  createdAt: string;
};

export type ProfileDetail = ProfileSummary & {
  contentHash: string;
  resumeText: string;
  experienceMinYears: number | null;
  experienceMaxYears: number | null;
  salaryMin: number | null;
  salaryMax: number | null;
  salaryCurrency: string | null;
};

export type ProfileWriteResult = ProfileDetail & { replayed: boolean };

export type ModelSummary = {
  id: string;
  name: string;
  contentHash: string;
  featureSchemaVersion: string;
  active: boolean;
  createdAt: string;
};

export type ModelDetail = ModelSummary & {
  artifactManifest: Record<string, unknown>;
  metrics: Record<string, unknown> | null;
};

export type ModelWriteResult = ModelDetail & { replayed: boolean };

export type EmailSettings = {
  enabled: boolean;
  senderName: string;
  sendAfterRanking: boolean;
  timezone: string;
  scheduledTime: string;
  transportConfigured: boolean;
  activeRecipientCount: number;
  recipientLimit: number;
};

export type EmailRecipient = {
  id: string;
  email: string;
  displayName: string | null;
  active: boolean;
  deletedAt: string | null;
  createdAt: string;
  updatedAt: string;
};

export type EmailRecipientWriteResult = EmailRecipient & {
  replayed: boolean;
  reactivated: boolean;
};

export type DashboardJob = {
  id: string;
  code: string;
  companyName: string;
  roleTitle: string;
  seniority: string | null;
  location: string | null;
  workMode: string | null;
  employmentType: string | null;
  description: string;
  salaryMin: number | null;
  salaryMax: number | null;
  salaryCurrency: string | null;
  postedAt: string | null;
  applyUrl: string;
  batchId: string;
  batchName: string;
  reviewStatus: string;
  applicationStatus: string;
  rank: number | null;
  jediPreferenceScore: number | null;
  rankingScore: number | null;
  applyPreferenceProbability: number | null;
  applyRecommendation: boolean | null;
  rankedAt: string | null;
};

export type DashboardFeed = {
  todayJobs: DashboardJob[];
  jobFeedScope: "today" | "latest";
  leaderboard: DashboardJob[];
  leaderboardPeriod: "daily" | "weekly" | "overall";
  fresh: boolean;
  notApplied: boolean;
  generatedAt: string;
};

export type LatestPrediction = {
  rank: number;
  jediPreferenceScore: number;
  applyPreferenceProbability: number;
  rankingScore: number;
  rankingStrategy: string;
  applyRecommendation: boolean | null;
  processingRunId: string;
  rankedAt: string;
};

export type JobListItem = {
  id: string;
  code: string;
  companyName: string;
  roleTitle: string;
  location: string | null;
  workMode: string | null;
  createdAt: string;
  relevanceLabel: string | null;
  reviewStatus: string;
  applicationStatus: string;
  annotationComplete: boolean;
  latestPrediction: LatestPrediction | null;
};

export type JobPage = {
  items: JobListItem[];
  page: number;
  pageSize: number;
  total: number;
};

export type JobStateResult = {
  jobId: string;
  relevanceLabel: string | null;
  reviewStatus: string;
  applicationStatus: string;
  viewedAt: string | null;
  notes: string | null;
  updatedAt: string;
};

export type JobAnnotationDetail = {
  applyLabel: boolean | null;
  roleTitleFit: number | null;
  roleFamilyFit: number | null;
  seniorityFit: number | null;
  locationFit: number | null;
  workModeFit: number | null;
  experienceFit: number | null;
  skillsFit: number | null;
  salaryFit: number | null;
  overallPreference: number | null;
  complete: boolean;
};

export type PredictionSummary = {
  id: string;
  rank: number;
  jediPreferenceScore: number;
  applyPreferenceProbability: number;
  componentScores: Record<string, number> | null;
  rankingScore: number;
  rankingStrategy: string;
  applyThreshold: number | null;
  modelApplyDecision: boolean | null;
  applyRecommendation: boolean | null;
  outputSchemaVersion: string;
  profileVersionId: string;
  modelVersionId: string;
  processingRunId: string;
  createdAt: string;
};

export type ApplicationRecord = {
  jobId: string;
  status: string;
  appliedAt: string | null;
  targetApplyBy: string | null;
  nextAction: string | null;
  nextActionDueAt: string | null;
  portalUrl: string | null;
  referenceCode: string | null;
  notes: string | null;
  closedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
};

export type ApplicationMilestone = {
  id: string;
  jobId: string;
  type: string;
  title: string;
  status: string;
  scheduledAt: string | null;
  completedAt: string | null;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
};

export type JobEvent = ApplicationEventResult;

export type JobDetail = {
  job: BatchJob;
  batch: BatchSummary;
  state: JobStateResult | null;
  annotation: JobAnnotationDetail | null;
  application: ApplicationRecord;
  milestones: ApplicationMilestone[];
  predictions: PredictionSummary[];
  events: JobEvent[];
};

export type ApplicationListItem = {
  job: JobListItem;
  notes: string | null;
  application: ApplicationRecord;
  latestEvent: JobEvent | null;
};

export type ApplicationPage = {
  items: ApplicationListItem[];
  page: number;
  pageSize: number;
  total: number;
  statusCounts: Record<string, number>;
  overdueCount: number;
};

export type ApplicationAction = {
  jobId: string;
  companyName: string;
  roleTitle: string;
  applicationStatus: string;
  nextAction: string;
  nextActionDueAt: string;
  applicationUpdatedAt: string;
};

export type ApplicationSummary = {
  statusCounts: Record<string, number>;
  overdueCount: number;
  dueTodayCount: number;
  nearestActions: ApplicationAction[];
};

export type BatchMetrics = {
  batchId: string;
  jobCount: number;
  rankedCount: number;
  averageScore: number | null;
  top25AverageScore: number | null;
  averageApplyProbability: number | null;
  recommendedCount: number;
  appliedCount: number;
  applicationRate: number;
  viewedCount: number;
  bookmarkedCount: number;
  scoreBuckets: Array<{ label: string; count: number }>;
  componentAverages: Record<string, number>;
};

export type ApplicationEventResult = {
  id: string;
  jobId: string;
  eventType: string;
  previousStatus: string | null;
  newStatus: string | null;
  notes: string | null;
  eventAt: string;
  createdAt: string;
};

export type RankingQueueResult = {
  batchId: string;
  status: string;
  processingRunId: string;
  pendingExecution: boolean;
};

export type RankingResult = {
  jobId: string;
  rank: number;
  rankingScore: number | null;
  jediPreferenceScore: number;
  applyPreferenceProbability: number;
  rankingStrategy: string;
  applyThreshold: number | null;
  modelApplyDecision: boolean | null;
  applyRecommendation: boolean | null;
  outputSchemaVersion: string;
  componentScores: Record<string, number> | null;
  profileVersionId: string;
  modelVersionId: string;
  processingRunId: string;
};

export type ModelInvocation = {
  id: string;
  attempt: number;
  status: string;
  artifactHash: string;
  inputCount: number;
  outputCount: number;
  coldStart: boolean | null;
  timingsMs: Record<string, number> | null;
  errorCode: string | null;
  rawResponse: Record<string, unknown> | null;
  startedAt: string;
  completedAt: string | null;
};

export type ProcessingRun = {
  id: string;
  stage: string;
  status: string;
  effectiveStatus: string;
  phase: string;
  attempt: number;
  retryable: boolean | null;
  trigger: string;
  retryOfRunId: string | null;
  profileVersionId: string | null;
  modelVersionId: string | null;
  modelName: string | null;
  featureSchemaVersion: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  startedAt: string | null;
  heartbeatAt: string | null;
  completedAt: string | null;
  createdAt: string;
  invocation: ModelInvocation | null;
};

export type RankingExecutionResult = {
  batchId: string;
  status: string;
  processingRunId: string;
  rankingCount: number;
  coldStart: boolean;
  timingsMs: Record<string, number>;
};

export type RankingRetryResult = RankingQueueResult & {
  retryOfRunId: string;
};

export type ModelRuntimeHealth = {
  state: "UNINITIALIZED" | "LOADING" | "READY" | "FAILED";
  ready: boolean;
  modelVersion: string | null;
  featureSchemaVersion: string | null;
  requestContractVersion: string | null;
  responseContractVersion: string | null;
  artifactHash: string | null;
  coldStart: boolean | null;
  modelLoadMs: number | null;
  smokeTestMs: number | null;
  errorCode: string | null;
};

export type ModelOperationResult = {
  status: "READY" | "FAILED";
  modelVersionId: string | null;
  deploymentId: string | null;
  checkId: string | null;
  runtime: ModelRuntimeHealth;
  details: Record<string, unknown>;
};

export type ModelRuntimeMetrics = {
  sampleSize: number;
  successCount: number;
  failureCount: number;
  failureRate: number;
  staleCount: number;
  coldStartRate: number;
  p95ExecutionMs: number | null;
  latestSuccessfulRankingAgeSeconds: number | null;
  runtime: ModelRuntimeHealth;
  warnings: string[];
};

function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (configured) return configured;
  if (
    typeof window !== "undefined" &&
    ["localhost", "127.0.0.1"].includes(window.location.hostname)
  ) {
    return "http://localhost:8000";
  }
  return "/svc/ml";
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "include",
      headers: {
        ...(init.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError(
      "The JEDI backend is unreachable. Check that the API server is running.",
      0,
      "NETWORK_ERROR",
    );
  }

  if (response.status === 204) return undefined as T;
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson
    ? ((await response.json()) as ApiErrorPayload & T)
    : undefined;

  if (!response.ok) {
    throw new ApiError(
      payload?.error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      payload?.error?.code ?? `HTTP_${response.status}`,
      payload?.error?.requestId ?? response.headers.get("x-request-id") ?? undefined,
      payload?.error?.details,
    );
  }
  return payload as T;
}

export const apiGet = <T>(path: string) => apiRequest<T>(path);

export async function timedGet<T>(path: string): Promise<TimedResult<T>> {
  const started = performance.now();
  const data = await apiGet<T>(path);
  return {
    data,
    latencyMs: Math.round(performance.now() - started),
    checkedAt: new Date().toISOString(),
  };
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function safeNext(value: string | null): string {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/dashboard";
}

export function errorSummary(error: unknown): string {
  return isApiError(error) ? error.message : "Something unexpected went wrong.";
}
