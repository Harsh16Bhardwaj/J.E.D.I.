CREATE TYPE "ScrapeRunStatus" AS ENUM (
  'CREATED', 'RUNNING', 'REVIEW_READY', 'IMPORTING', 'IMPORTED', 'FAILED', 'CANCELLED'
);

CREATE TYPE "ScrapeAttemptStatus" AS ENUM (
  'PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED'
);

CREATE TABLE "ScrapeRun" (
  "id" TEXT NOT NULL,
  "groupId" TEXT NOT NULL,
  "status" "ScrapeRunStatus" NOT NULL DEFAULT 'CREATED',
  "configVersion" TEXT NOT NULL,
  "configHash" TEXT NOT NULL,
  "targetJobCount" INTEGER NOT NULL DEFAULT 100,
  "brightDataLimit" INTEGER NOT NULL DEFAULT 150,
  "brightDataUsed" INTEGER NOT NULL DEFAULT 0,
  "discoveredCount" INTEGER NOT NULL DEFAULT 0,
  "validCount" INTEGER NOT NULL DEFAULT 0,
  "selectedCount" INTEGER NOT NULL DEFAULT 0,
  "failedSourceCount" INTEGER NOT NULL DEFAULT 0,
  "importedBatchId" TEXT,
  "errorMessage" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "completedAt" TIMESTAMP(3),
  CONSTRAINT "ScrapeRun_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "ScrapeAttempt" (
  "id" TEXT NOT NULL,
  "runId" TEXT NOT NULL,
  "stepKey" TEXT NOT NULL,
  "sourceKey" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "status" "ScrapeAttemptStatus" NOT NULL DEFAULT 'PENDING',
  "attemptCount" INTEGER NOT NULL DEFAULT 0,
  "discoveredCount" INTEGER NOT NULL DEFAULT 0,
  "validCount" INTEGER NOT NULL DEFAULT 0,
  "brightDataUsed" INTEGER NOT NULL DEFAULT 0,
  "errorMessage" TEXT,
  "leaseExpiresAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ScrapeAttempt_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "ScrapeCandidate" (
  "id" TEXT NOT NULL,
  "runId" TEXT NOT NULL,
  "sourceKey" TEXT NOT NULL,
  "sourceProvider" TEXT NOT NULL,
  "sourceUrl" TEXT NOT NULL,
  "canonicalUrl" TEXT NOT NULL,
  "companyName" TEXT NOT NULL,
  "roleTitle" TEXT NOT NULL,
  "location" TEXT,
  "experienceMinYears" DOUBLE PRECISION,
  "experienceMaxYears" DOUBLE PRECISION,
  "postedAt" TIMESTAMP(3),
  "payload" JSONB NOT NULL,
  "schemaValid" BOOLEAN NOT NULL DEFAULT false,
  "selected" BOOLEAN NOT NULL DEFAULT false,
  "validationErrors" JSONB,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ScrapeCandidate_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "ScrapeSource" (
  "id" TEXT NOT NULL,
  "groupId" TEXT NOT NULL,
  "sourceKey" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "atsType" TEXT NOT NULL,
  "domainHint" TEXT NOT NULL,
  "boardToken" TEXT NOT NULL,
  "discovered" BOOLEAN NOT NULL DEFAULT false,
  "active" BOOLEAN NOT NULL DEFAULT true,
  "lastSeenAt" TIMESTAMP(3),
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ScrapeSource_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ScrapeRun_importedBatchId_key" ON "ScrapeRun"("importedBatchId");
CREATE INDEX "ScrapeRun_groupId_createdAt_idx" ON "ScrapeRun"("groupId", "createdAt");
CREATE INDEX "ScrapeRun_status_updatedAt_idx" ON "ScrapeRun"("status", "updatedAt");
CREATE UNIQUE INDEX "ScrapeAttempt_runId_stepKey_key" ON "ScrapeAttempt"("runId", "stepKey");
CREATE INDEX "ScrapeAttempt_runId_status_createdAt_idx" ON "ScrapeAttempt"("runId", "status", "createdAt");
CREATE UNIQUE INDEX "ScrapeCandidate_runId_canonicalUrl_key" ON "ScrapeCandidate"("runId", "canonicalUrl");
CREATE INDEX "ScrapeCandidate_runId_schemaValid_selected_idx" ON "ScrapeCandidate"("runId", "schemaValid", "selected");
CREATE UNIQUE INDEX "ScrapeSource_groupId_sourceKey_key" ON "ScrapeSource"("groupId", "sourceKey");
CREATE INDEX "ScrapeSource_groupId_atsType_active_idx" ON "ScrapeSource"("groupId", "atsType", "active");

ALTER TABLE "ScrapeRun" ADD CONSTRAINT "ScrapeRun_groupId_fkey"
  FOREIGN KEY ("groupId") REFERENCES "Group"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ScrapeRun" ADD CONSTRAINT "ScrapeRun_importedBatchId_fkey"
  FOREIGN KEY ("importedBatchId") REFERENCES "Batch"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "ScrapeAttempt" ADD CONSTRAINT "ScrapeAttempt_runId_fkey"
  FOREIGN KEY ("runId") REFERENCES "ScrapeRun"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ScrapeCandidate" ADD CONSTRAINT "ScrapeCandidate_runId_fkey"
  FOREIGN KEY ("runId") REFERENCES "ScrapeRun"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ScrapeSource" ADD CONSTRAINT "ScrapeSource_groupId_fkey"
  FOREIGN KEY ("groupId") REFERENCES "Group"("id") ON DELETE CASCADE ON UPDATE CASCADE;
