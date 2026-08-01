-- Extend delivery and campaign state without removing the existing sender's
-- batch-specific compatibility columns. EmailDelivery is currently empty in
-- Neon, but the additive transition keeps local APIs usable between chunks.
ALTER TYPE "EmailStatus" ADD VALUE 'CANCELLED';

CREATE TYPE "EmailCampaignStatus" AS ENUM (
    'WAITING_FOR_RANKINGS',
    'PENDING',
    'SENDING',
    'SENT',
    'PARTIAL_FAILED',
    'FAILED',
    'SKIPPED',
    'EXPIRED'
);

-- Structured immutable model-card metadata. Defaults preserve the existing
-- metadata-only registry row until deployment APIs are introduced.
ALTER TABLE "ModelVersion"
ADD COLUMN "description" TEXT NOT NULL DEFAULT '',
ADD COLUMN "modelFamily" TEXT NOT NULL DEFAULT 'legacy',
ADD COLUMN "requestContractVersion" TEXT NOT NULL DEFAULT 'jedi-ranking-v1',
ADD COLUMN "tags" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
ADD COLUMN "trainingMetadata" JSONB,
ADD COLUMN "evaluationMetadata" JSONB;

ALTER TABLE "ProcessingRun" ADD COLUMN "nextAttemptAt" TIMESTAMP(3);

DROP INDEX "ProcessingRun_stage_status_leaseExpiresAt_createdAt_idx";
CREATE INDEX "ProcessingRun_stage_status_nextAttemptAt_leaseExpiresAt_createdAt_idx"
ON "ProcessingRun"("stage", "status", "nextAttemptAt", "leaseExpiresAt", "createdAt");

CREATE TABLE "ModelDeployment" (
    "id" TEXT NOT NULL,
    "modelVersionId" TEXT NOT NULL,
    "endpointUrl" TEXT NOT NULL,
    "healthUrl" TEXT NOT NULL,
    "timeoutSeconds" INTEGER NOT NULL DEFAULT 120,
    "healthVerifiedAt" TIMESTAMP(3),
    "lastHealthStatus" TEXT,
    "lastHealthLatencyMs" INTEGER,
    "lastHealthErrorCode" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ModelDeployment_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "ModelEndpointCheck" (
    "id" TEXT NOT NULL,
    "modelVersionId" TEXT NOT NULL,
    "deploymentId" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "latencyMs" INTEGER,
    "httpStatus" INTEGER,
    "errorCode" TEXT,
    "healthUrlSnapshot" TEXT NOT NULL,
    "returnedFeatureSchemaVersion" TEXT,
    "returnedRequestContractVersion" TEXT,
    "checkedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ModelEndpointCheck_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ModelDeployment_modelVersionId_key"
ON "ModelDeployment"("modelVersionId");

CREATE INDEX "ModelEndpointCheck_modelVersionId_checkedAt_idx"
ON "ModelEndpointCheck"("modelVersionId", "checkedAt");

ALTER TABLE "ModelDeployment"
ADD CONSTRAINT "ModelDeployment_modelVersionId_fkey"
FOREIGN KEY ("modelVersionId") REFERENCES "ModelVersion"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "ModelEndpointCheck"
ADD CONSTRAINT "ModelEndpointCheck_modelVersionId_fkey"
FOREIGN KEY ("modelVersionId") REFERENCES "ModelVersion"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "ModelEndpointCheck"
ADD CONSTRAINT "ModelEndpointCheck_deploymentId_fkey"
FOREIGN KEY ("deploymentId") REFERENCES "ModelDeployment"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "EmailConfiguration" (
    "id" TEXT NOT NULL DEFAULT 'default',
    "enabled" BOOLEAN NOT NULL DEFAULT false,
    "senderName" TEXT NOT NULL DEFAULT 'JEDI Daily Dispatch',
    "sendAfterRanking" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "EmailConfiguration_pkey" PRIMARY KEY ("id")
);

INSERT INTO "EmailConfiguration" (
    "id", "enabled", "senderName", "sendAfterRanking", "updatedAt"
) VALUES (
    'default', false, 'JEDI Daily Dispatch', true, CURRENT_TIMESTAMP
);

CREATE TABLE "EmailRecipient" (
    "id" TEXT NOT NULL,
    "configurationId" TEXT NOT NULL DEFAULT 'default',
    "email" TEXT NOT NULL,
    "emailNormalized" TEXT NOT NULL,
    "displayName" TEXT,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "deletedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "EmailRecipient_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "EmailRecipient_emailNormalized_key"
ON "EmailRecipient"("emailNormalized");

CREATE INDEX "EmailRecipient_active_deletedAt_idx"
ON "EmailRecipient"("active", "deletedAt");

ALTER TABLE "EmailRecipient"
ADD CONSTRAINT "EmailRecipient_configurationId_fkey"
FOREIGN KEY ("configurationId") REFERENCES "EmailConfiguration"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE TABLE "EmailCampaign" (
    "id" TEXT NOT NULL,
    "campaignDate" DATE NOT NULL,
    "digestType" TEXT NOT NULL DEFAULT 'DAILY_TOP_10',
    "status" "EmailCampaignStatus" NOT NULL DEFAULT 'WAITING_FOR_RANKINGS',
    "scheduledAt" TIMESTAMP(3) NOT NULL,
    "templateVersion" TEXT NOT NULL DEFAULT 'daily-top-10-v1',
    "payloadSnapshot" JSONB,
    "selectedJobCount" INTEGER NOT NULL DEFAULT 0,
    "recipientCount" INTEGER NOT NULL DEFAULT 0,
    "sentCount" INTEGER NOT NULL DEFAULT 0,
    "failedCount" INTEGER NOT NULL DEFAULT 0,
    "cancelledCount" INTEGER NOT NULL DEFAULT 0,
    "failureReason" TEXT,
    "lastReconciledAt" TIMESTAMP(3),
    "queuedAt" TIMESTAMP(3),
    "sentAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "EmailCampaign_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "EmailCampaign_campaignDate_digestType_key"
ON "EmailCampaign"("campaignDate", "digestType");

CREATE INDEX "EmailCampaign_status_scheduledAt_idx"
ON "EmailCampaign"("status", "scheduledAt");

CREATE TABLE "EmailCampaignRun" (
    "campaignId" TEXT NOT NULL,
    "processingRunId" TEXT NOT NULL,
    "addedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "EmailCampaignRun_pkey"
    PRIMARY KEY ("campaignId", "processingRunId")
);

CREATE INDEX "EmailCampaignRun_processingRunId_idx"
ON "EmailCampaignRun"("processingRunId");

ALTER TABLE "EmailCampaignRun"
ADD CONSTRAINT "EmailCampaignRun_campaignId_fkey"
FOREIGN KEY ("campaignId") REFERENCES "EmailCampaign"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "EmailCampaignRun"
ADD CONSTRAINT "EmailCampaignRun_processingRunId_fkey"
FOREIGN KEY ("processingRunId") REFERENCES "ProcessingRun"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

-- New campaign deliveries use campaignId and recipientId. The existing
-- batchId/rankingRunId columns become nullable so the old sender can coexist
-- until its compatibility routes delegate to campaigns.
ALTER TABLE "EmailDelivery"
ALTER COLUMN "batchId" DROP NOT NULL,
ALTER COLUMN "rankingRunId" DROP NOT NULL,
ADD COLUMN "campaignId" TEXT,
ADD COLUMN "recipientId" TEXT,
ADD COLUMN "recipientDisplayName" TEXT,
ADD COLUMN "retryCycle" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN "retryCycleAttempts" INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX "EmailDelivery_campaignId_recipientId_key"
ON "EmailDelivery"("campaignId", "recipientId");

CREATE INDEX "EmailDelivery_campaignId_status_idx"
ON "EmailDelivery"("campaignId", "status");

ALTER TABLE "EmailDelivery"
ADD CONSTRAINT "EmailDelivery_campaignId_fkey"
FOREIGN KEY ("campaignId") REFERENCES "EmailCampaign"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "EmailDelivery"
ADD CONSTRAINT "EmailDelivery_recipientId_fkey"
FOREIGN KEY ("recipientId") REFERENCES "EmailRecipient"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
