ALTER TYPE "EmailStatus" ADD VALUE IF NOT EXISTS 'BLOCKED';

-- Ranking-run history supersedes the legacy one-delivery-per-batch constraint.
DROP INDEX IF EXISTS "EmailDelivery_batchId_recipient_key";

CREATE TABLE "EmailDeliveryAttempt" (
    "id" TEXT NOT NULL,
    "emailDeliveryId" TEXT NOT NULL,
    "attemptNumber" INTEGER NOT NULL,
    "retryCycle" INTEGER NOT NULL,
    "trigger" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "requestedByGroupMemberId" TEXT,
    "startedAt" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completedAt" TIMESTAMPTZ,
    "providerMessageId" TEXT,
    "errorCode" TEXT,
    "safeErrorMessage" TEXT,
    CONSTRAINT "EmailDeliveryAttempt_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "EmailDeliveryAttempt_emailDeliveryId_fkey" FOREIGN KEY ("emailDeliveryId") REFERENCES "EmailDelivery"("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "EmailDeliveryAttempt_requestedByGroupMemberId_fkey" FOREIGN KEY ("requestedByGroupMemberId") REFERENCES "GroupMember"("id") ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "EmailDelivery_batchId_rankingRunId_groupMemberId_key"
ON "EmailDelivery"("batchId", "rankingRunId", "groupMemberId");
CREATE INDEX "EmailDelivery_createdAt_id_idx" ON "EmailDelivery"("createdAt", "id");
CREATE INDEX "EmailDelivery_batchId_createdAt_idx" ON "EmailDelivery"("batchId", "createdAt");
CREATE INDEX "EmailDelivery_recipientId_createdAt_idx" ON "EmailDelivery"("recipientId", "createdAt");
CREATE INDEX "EmailDelivery_groupMemberId_createdAt_idx" ON "EmailDelivery"("groupMemberId", "createdAt");
CREATE UNIQUE INDEX "EmailDeliveryAttempt_emailDeliveryId_retryCycle_attemptNumber_key"
ON "EmailDeliveryAttempt"("emailDeliveryId", "retryCycle", "attemptNumber");
CREATE INDEX "EmailDeliveryAttempt_emailDeliveryId_startedAt_idx"
ON "EmailDeliveryAttempt"("emailDeliveryId", "startedAt");
CREATE INDEX "EmailDeliveryAttempt_requestedByGroupMemberId_startedAt_idx"
ON "EmailDeliveryAttempt"("requestedByGroupMemberId", "startedAt");
