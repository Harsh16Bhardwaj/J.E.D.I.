-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "BatchStatus" AS ENUM ('READY', 'NORMALIZING', 'NORMALIZED', 'RANK_PENDING', 'RANKING', 'RANKED', 'FAILED');

-- CreateEnum
CREATE TYPE "RelevanceLabel" AS ENUM ('DREAM', 'STRONG_APPLY', 'CONSIDER', 'REJECT');

-- CreateEnum
CREATE TYPE "ReviewStatus" AS ENUM ('NEW', 'VIEWED', 'SAVED', 'DISMISSED');

-- CreateEnum
CREATE TYPE "ApplicationStatus" AS ENUM ('NOT_STARTED', 'PREPARING', 'APPLIED', 'ASSESSMENT', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN');

-- CreateEnum
CREATE TYPE "ProcessingStatus" AS ENUM ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED');

-- CreateEnum
CREATE TYPE "EmailStatus" AS ENUM ('PENDING', 'SENT', 'FAILED');

-- CreateTable
CREATE TABLE "User" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "User_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Batch" (
    "id" TEXT NOT NULL,
    "externalBatchId" TEXT NOT NULL,
    "contentHash" TEXT NOT NULL,
    "schemaVersion" TEXT NOT NULL,
    "promptVersion" TEXT,
    "generatedAt" TIMESTAMP(3) NOT NULL,
    "rawEnvelope" JSONB NOT NULL,
    "status" "BatchStatus" NOT NULL DEFAULT 'READY',
    "receivedCount" INTEGER NOT NULL DEFAULT 0,
    "validCount" INTEGER NOT NULL DEFAULT 0,
    "duplicateCount" INTEGER NOT NULL DEFAULT 0,
    "jobCount" INTEGER NOT NULL DEFAULT 0,
    "validationReport" JSONB,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "rankedAt" TIMESTAMP(3),

    CONSTRAINT "Batch_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Job" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "dedupeKey" TEXT NOT NULL,
    "companyKey" TEXT NOT NULL,
    "batchId" TEXT NOT NULL,
    "companyName" TEXT NOT NULL,
    "roleTitle" TEXT NOT NULL,
    "roleFamily" TEXT,
    "seniority" TEXT,
    "location" TEXT,
    "workMode" TEXT,
    "employmentType" TEXT,
    "description" TEXT NOT NULL,
    "skills" TEXT[],
    "experienceMinYears" DOUBLE PRECISION,
    "experienceMaxYears" DOUBLE PRECISION,
    "salaryMin" DECIMAL(14,2),
    "salaryMax" DECIMAL(14,2),
    "salaryCurrency" TEXT,
    "postedAt" TIMESTAMP(3),
    "applicationDeadline" TIMESTAMP(3),
    "canApplyNow" BOOLEAN,
    "applyUrl" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Job_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ProfileVersion" (
    "id" TEXT NOT NULL,
    "contentHash" TEXT NOT NULL,
    "resumeText" TEXT NOT NULL,
    "preferredTitles" TEXT[],
    "preferredLocations" TEXT[],
    "preferredSkills" TEXT[],
    "experienceMinYears" DOUBLE PRECISION,
    "experienceMaxYears" DOUBLE PRECISION,
    "salaryMin" DECIMAL(14,2),
    "salaryMax" DECIMAL(14,2),
    "salaryCurrency" TEXT,
    "active" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ProfileVersion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PreparedJob" (
    "id" TEXT NOT NULL,
    "featureSchemaVersion" TEXT NOT NULL,
    "payloadHash" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "jobId" TEXT NOT NULL,
    "profileVersionId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "PreparedJob_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "JobAnnotation" (
    "jobId" TEXT NOT NULL,
    "applyLabel" BOOLEAN,
    "roleTitleFit" DOUBLE PRECISION,
    "roleFamilyFit" DOUBLE PRECISION,
    "seniorityFit" DOUBLE PRECISION,
    "locationFit" DOUBLE PRECISION,
    "workModeFit" DOUBLE PRECISION,
    "experienceFit" DOUBLE PRECISION,
    "skillsFit" DOUBLE PRECISION,
    "salaryFit" DOUBLE PRECISION,
    "overallPreference" DOUBLE PRECISION,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "JobAnnotation_pkey" PRIMARY KEY ("jobId")
);

-- CreateTable
CREATE TABLE "TrainingExample" (
    "id" TEXT NOT NULL,
    "featureSchemaVersion" TEXT NOT NULL,
    "featurePayload" JSONB NOT NULL,
    "applyLabel" BOOLEAN NOT NULL,
    "roleTitleFit" DOUBLE PRECISION NOT NULL,
    "roleFamilyFit" DOUBLE PRECISION NOT NULL,
    "seniorityFit" DOUBLE PRECISION NOT NULL,
    "locationFit" DOUBLE PRECISION NOT NULL,
    "workModeFit" DOUBLE PRECISION NOT NULL,
    "experienceFit" DOUBLE PRECISION NOT NULL,
    "skillsFit" DOUBLE PRECISION NOT NULL,
    "salaryFit" DOUBLE PRECISION NOT NULL,
    "overallPreference" DOUBLE PRECISION NOT NULL,
    "jobId" TEXT NOT NULL,
    "batchId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "TrainingExample_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ModelVersion" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "artifactManifest" JSONB NOT NULL,
    "featureSchemaVersion" TEXT NOT NULL,
    "metrics" JSONB,
    "active" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ModelVersion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "JobPrediction" (
    "id" TEXT NOT NULL,
    "rank" INTEGER NOT NULL,
    "jediPreferenceScore" DOUBLE PRECISION NOT NULL,
    "applyPreferenceProbability" DOUBLE PRECISION NOT NULL,
    "componentScores" JSONB,
    "jobId" TEXT NOT NULL,
    "batchId" TEXT NOT NULL,
    "profileVersionId" TEXT NOT NULL,
    "modelVersionId" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "JobPrediction_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "JobState" (
    "jobId" TEXT NOT NULL,
    "relevanceLabel" "RelevanceLabel",
    "reviewStatus" "ReviewStatus" NOT NULL DEFAULT 'NEW',
    "applicationStatus" "ApplicationStatus" NOT NULL DEFAULT 'NOT_STARTED',
    "notes" TEXT,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "JobState_pkey" PRIMARY KEY ("jobId")
);

-- CreateTable
CREATE TABLE "JobEvent" (
    "id" TEXT NOT NULL,
    "jobId" TEXT NOT NULL,
    "eventType" TEXT NOT NULL,
    "notes" TEXT,
    "eventAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "JobEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ProcessingRun" (
    "id" TEXT NOT NULL,
    "batchId" TEXT NOT NULL,
    "idempotencyKey" TEXT NOT NULL,
    "status" "ProcessingStatus" NOT NULL DEFAULT 'QUEUED',
    "stage" TEXT NOT NULL,
    "attempt" INTEGER NOT NULL DEFAULT 0,
    "leaseToken" TEXT,
    "leaseExpiresAt" TIMESTAMP(3),
    "heartbeatAt" TIMESTAMP(3),
    "errorCode" TEXT,
    "errorMessage" TEXT,
    "startedAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ProcessingRun_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "EmailDelivery" (
    "id" TEXT NOT NULL,
    "batchId" TEXT NOT NULL,
    "recipient" TEXT NOT NULL,
    "status" "EmailStatus" NOT NULL DEFAULT 'PENDING',
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "providerMessageId" TEXT,
    "payloadSnapshot" JSONB NOT NULL,
    "lastError" TEXT,
    "sentAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "EmailDelivery_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "User_email_key" ON "User"("email");

-- CreateIndex
CREATE UNIQUE INDEX "Batch_externalBatchId_key" ON "Batch"("externalBatchId");

-- CreateIndex
CREATE UNIQUE INDEX "Batch_contentHash_key" ON "Batch"("contentHash");

-- CreateIndex
CREATE INDEX "Batch_status_createdAt_idx" ON "Batch"("status", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "Job_code_key" ON "Job"("code");

-- CreateIndex
CREATE UNIQUE INDEX "Job_dedupeKey_key" ON "Job"("dedupeKey");

-- CreateIndex
CREATE INDEX "Job_companyKey_idx" ON "Job"("companyKey");

-- CreateIndex
CREATE INDEX "Job_companyKey_roleTitle_idx" ON "Job"("companyKey", "roleTitle");

-- CreateIndex
CREATE INDEX "Job_batchId_idx" ON "Job"("batchId");

-- CreateIndex
CREATE UNIQUE INDEX "ProfileVersion_contentHash_key" ON "ProfileVersion"("contentHash");

-- CreateIndex
CREATE INDEX "ProfileVersion_active_idx" ON "ProfileVersion"("active");

-- CreateIndex
CREATE INDEX "PreparedJob_profileVersionId_featureSchemaVersion_idx" ON "PreparedJob"("profileVersionId", "featureSchemaVersion");

-- CreateIndex
CREATE UNIQUE INDEX "PreparedJob_jobId_profileVersionId_featureSchemaVersion_key" ON "PreparedJob"("jobId", "profileVersionId", "featureSchemaVersion");

-- CreateIndex
CREATE INDEX "TrainingExample_batchId_idx" ON "TrainingExample"("batchId");

-- CreateIndex
CREATE UNIQUE INDEX "TrainingExample_jobId_featureSchemaVersion_key" ON "TrainingExample"("jobId", "featureSchemaVersion");

-- CreateIndex
CREATE UNIQUE INDEX "ModelVersion_name_key" ON "ModelVersion"("name");

-- CreateIndex
CREATE INDEX "ModelVersion_active_idx" ON "ModelVersion"("active");

-- CreateIndex
CREATE INDEX "JobPrediction_batchId_rank_idx" ON "JobPrediction"("batchId", "rank");

-- CreateIndex
CREATE UNIQUE INDEX "JobPrediction_jobId_batchId_profileVersionId_modelVersionId_key" ON "JobPrediction"("jobId", "batchId", "profileVersionId", "modelVersionId");

-- CreateIndex
CREATE INDEX "JobEvent_jobId_eventAt_idx" ON "JobEvent"("jobId", "eventAt");

-- CreateIndex
CREATE UNIQUE INDEX "ProcessingRun_idempotencyKey_key" ON "ProcessingRun"("idempotencyKey");

-- CreateIndex
CREATE INDEX "ProcessingRun_batchId_status_idx" ON "ProcessingRun"("batchId", "status");

-- CreateIndex
CREATE INDEX "ProcessingRun_stage_status_leaseExpiresAt_createdAt_idx" ON "ProcessingRun"("stage", "status", "leaseExpiresAt", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "EmailDelivery_batchId_recipient_key" ON "EmailDelivery"("batchId", "recipient");

-- AddForeignKey
ALTER TABLE "Job" ADD CONSTRAINT "Job_batchId_fkey" FOREIGN KEY ("batchId") REFERENCES "Batch"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PreparedJob" ADD CONSTRAINT "PreparedJob_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "Job"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PreparedJob" ADD CONSTRAINT "PreparedJob_profileVersionId_fkey" FOREIGN KEY ("profileVersionId") REFERENCES "ProfileVersion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "JobAnnotation" ADD CONSTRAINT "JobAnnotation_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "Job"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TrainingExample" ADD CONSTRAINT "TrainingExample_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "Job"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "TrainingExample" ADD CONSTRAINT "TrainingExample_batchId_fkey" FOREIGN KEY ("batchId") REFERENCES "Batch"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "JobPrediction" ADD CONSTRAINT "JobPrediction_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "Job"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "JobPrediction" ADD CONSTRAINT "JobPrediction_batchId_fkey" FOREIGN KEY ("batchId") REFERENCES "Batch"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "JobPrediction" ADD CONSTRAINT "JobPrediction_profileVersionId_fkey" FOREIGN KEY ("profileVersionId") REFERENCES "ProfileVersion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "JobPrediction" ADD CONSTRAINT "JobPrediction_modelVersionId_fkey" FOREIGN KEY ("modelVersionId") REFERENCES "ModelVersion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "JobState" ADD CONSTRAINT "JobState_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "Job"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "JobEvent" ADD CONSTRAINT "JobEvent_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "Job"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ProcessingRun" ADD CONSTRAINT "ProcessingRun_batchId_fkey" FOREIGN KEY ("batchId") REFERENCES "Batch"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EmailDelivery" ADD CONSTRAINT "EmailDelivery_batchId_fkey" FOREIGN KEY ("batchId") REFERENCES "Batch"("id") ON DELETE CASCADE ON UPDATE CASCADE;
