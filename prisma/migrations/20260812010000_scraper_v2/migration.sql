CREATE TYPE "SourceDiscoveryRunStatus" AS ENUM (
  'CREATED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'
);

ALTER TABLE "ScrapeAttempt"
  ADD COLUMN "checkpoint" JSONB,
  ADD COLUMN "responseTimeMs" INTEGER,
  ADD COLUMN "freeRequestCount" INTEGER NOT NULL DEFAULT 0;

ALTER TABLE "ScrapeCandidate"
  ADD COLUMN "freshnessTier" TEXT NOT NULL DEFAULT 'REJECTED',
  ADD COLUMN "qualityScore" DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN "reviewGroup" TEXT NOT NULL DEFAULT 'REJECTED',
  ADD COLUMN "extractedFacts" JSONB,
  ADD COLUMN "evidenceSpans" JSONB,
  ADD COLUMN "extractionVersion" TEXT,
  ADD COLUMN "descriptionFingerprint" TEXT;

ALTER TABLE "ScrapeSource"
  ADD COLUMN "healthStatus" TEXT NOT NULL DEFAULT 'UNKNOWN',
  ADD COLUMN "lastSuccessAt" TIMESTAMPTZ,
  ADD COLUMN "lastFailureAt" TIMESTAMPTZ,
  ADD COLUMN "consecutiveFailures" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "consecutiveZeroYield" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "responseTimeMs" INTEGER,
  ADD COLUMN "jobsScanned" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "eligibleYield" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "duplicateYield" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "cooldownUntil" TIMESTAMPTZ,
  ADD COLUMN "etag" TEXT,
  ADD COLUMN "lastModified" TEXT,
  ADD COLUMN "responseCache" JSONB,
  ADD COLUMN "lastCheckpoint" JSONB;

CREATE INDEX "ScrapeSource_groupId_healthStatus_cooldownUntil_idx"
  ON "ScrapeSource"("groupId", "healthStatus", "cooldownUntil");

CREATE TABLE "ScrapeProviderUse" (
  "id" TEXT NOT NULL,
  "runId" TEXT NOT NULL,
  "attemptId" TEXT,
  "candidateUrl" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "units" INTEGER NOT NULL DEFAULT 1,
  "reason" TEXT NOT NULL,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ScrapeProviderUse_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "ScrapeProviderUse_runId_fkey" FOREIGN KEY ("runId")
    REFERENCES "ScrapeRun"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX "ScrapeProviderUse_runId_createdAt_idx"
  ON "ScrapeProviderUse"("runId", "createdAt");

CREATE TABLE "SourceDiscoveryRun" (
  "id" TEXT NOT NULL,
  "groupId" TEXT NOT NULL,
  "status" "SourceDiscoveryRunStatus" NOT NULL DEFAULT 'CREATED',
  "configVersion" TEXT NOT NULL,
  "configHash" TEXT NOT NULL,
  "totalHints" INTEGER NOT NULL DEFAULT 0,
  "processedHints" INTEGER NOT NULL DEFAULT 0,
  "detectedSources" INTEGER NOT NULL DEFAULT 0,
  "activatedSources" INTEGER NOT NULL DEFAULT 0,
  "failedHints" INTEGER NOT NULL DEFAULT 0,
  "errorMessage" TEXT,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ NOT NULL,
  "completedAt" TIMESTAMPTZ,
  CONSTRAINT "SourceDiscoveryRun_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "SourceDiscoveryRun_groupId_fkey" FOREIGN KEY ("groupId")
    REFERENCES "Group"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX "SourceDiscoveryRun_groupId_createdAt_idx"
  ON "SourceDiscoveryRun"("groupId", "createdAt");
CREATE INDEX "SourceDiscoveryRun_status_updatedAt_idx"
  ON "SourceDiscoveryRun"("status", "updatedAt");

CREATE TABLE "SourceDiscoveryAttempt" (
  "id" TEXT NOT NULL,
  "runId" TEXT NOT NULL,
  "stepKey" TEXT NOT NULL,
  "companyName" TEXT NOT NULL,
  "companyDomain" TEXT NOT NULL,
  "status" "ScrapeAttemptStatus" NOT NULL DEFAULT 'PENDING',
  "attemptCount" INTEGER NOT NULL DEFAULT 0,
  "detectedCount" INTEGER NOT NULL DEFAULT 0,
  "activatedCount" INTEGER NOT NULL DEFAULT 0,
  "responseTimeMs" INTEGER,
  "errorMessage" TEXT,
  "leaseExpiresAt" TIMESTAMPTZ,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ NOT NULL,
  CONSTRAINT "SourceDiscoveryAttempt_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "SourceDiscoveryAttempt_runId_fkey" FOREIGN KEY ("runId")
    REFERENCES "SourceDiscoveryRun"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "SourceDiscoveryAttempt_runId_stepKey_key"
  ON "SourceDiscoveryAttempt"("runId", "stepKey");
CREATE INDEX "SourceDiscoveryAttempt_runId_status_createdAt_idx"
  ON "SourceDiscoveryAttempt"("runId", "status", "createdAt");
