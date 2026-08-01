BEGIN;

ALTER TABLE "ModelDeployment"
ADD COLUMN "kind" TEXT NOT NULL DEFAULT 'EMBEDDED',
ADD COLUMN "artifactLocation" TEXT,
ADD COLUMN "deployedRevision" TEXT,
ALTER COLUMN "endpointUrl" DROP NOT NULL,
ALTER COLUMN "healthUrl" DROP NOT NULL;

ALTER TABLE "ModelEndpointCheck"
ADD COLUMN "returnedResponseContractVersion" TEXT,
ADD COLUMN "returnedArtifactHash" TEXT,
ADD COLUMN "coldStart" BOOLEAN,
ADD COLUMN "modelLoadMs" INTEGER,
ADD COLUMN "smokeTestMs" INTEGER,
ALTER COLUMN "healthUrlSnapshot" DROP NOT NULL;

ALTER TABLE "JobPrediction"
ADD COLUMN "rankingScore" DOUBLE PRECISION,
ADD COLUMN "rankingStrategy" TEXT NOT NULL DEFAULT 'legacy_jedi_v1',
ADD COLUMN "applyThreshold" DOUBLE PRECISION,
ADD COLUMN "modelApplyDecision" BOOLEAN,
ADD COLUMN "applyRecommendation" BOOLEAN,
ADD COLUMN "outputSchemaVersion" TEXT NOT NULL DEFAULT 'legacy-ranking-v1';

UPDATE "JobPrediction"
SET "rankingScore" = "jediPreferenceScore";

ALTER TABLE "JobPrediction"
ALTER COLUMN "rankingScore" SET NOT NULL;

ALTER TABLE "ProcessingRun"
ADD COLUMN "phase" TEXT NOT NULL DEFAULT 'QUEUED',
ADD COLUMN "retryable" BOOLEAN,
ADD COLUMN "trigger" TEXT NOT NULL DEFAULT 'USER',
ADD COLUMN "retryOfRunId" TEXT;

ALTER TABLE "ProcessingRun"
ADD CONSTRAINT "ProcessingRun_retryOfRunId_fkey"
FOREIGN KEY ("retryOfRunId") REFERENCES "ProcessingRun"("id")
ON DELETE SET NULL ON UPDATE CASCADE;

CREATE INDEX "ProcessingRun_retryOfRunId_idx"
ON "ProcessingRun"("retryOfRunId");

CREATE TABLE "ModelInvocation" (
    "id" TEXT NOT NULL,
    "processingRunId" TEXT NOT NULL,
    "modelVersionId" TEXT NOT NULL,
    "attempt" INTEGER NOT NULL,
    "status" TEXT NOT NULL,
    "requestContractVersion" TEXT NOT NULL,
    "responseContractVersion" TEXT NOT NULL,
    "featureSchemaVersion" TEXT NOT NULL,
    "artifactHash" TEXT NOT NULL,
    "inputHash" TEXT NOT NULL,
    "inputCount" INTEGER NOT NULL,
    "outputCount" INTEGER NOT NULL DEFAULT 0,
    "rawResponse" JSONB,
    "coldStart" BOOLEAN,
    "timingsMs" JSONB,
    "errorCode" TEXT,
    "errorMessage" TEXT,
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMP(3),
    CONSTRAINT "ModelInvocation_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ModelInvocation_processingRunId_attempt_key"
ON "ModelInvocation"("processingRunId", "attempt");

CREATE INDEX "ModelInvocation_modelVersionId_startedAt_idx"
ON "ModelInvocation"("modelVersionId", "startedAt");

ALTER TABLE "ModelInvocation"
ADD CONSTRAINT "ModelInvocation_processingRunId_fkey"
FOREIGN KEY ("processingRunId") REFERENCES "ProcessingRun"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "ModelInvocation"
ADD CONSTRAINT "ModelInvocation_modelVersionId_fkey"
FOREIGN KEY ("modelVersionId") REFERENCES "ModelVersion"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

COMMIT;
