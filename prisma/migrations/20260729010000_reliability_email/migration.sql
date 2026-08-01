-- AlterEnum
ALTER TYPE "EmailStatus" ADD VALUE 'SENDING';

-- DropIndex
DROP INDEX "JobPrediction_jobId_batchId_profileVersionId_modelVersionId_key";

-- DropIndex
DROP INDEX "TrainingExample_jobId_featureSchemaVersion_key";

-- AlterTable
ALTER TABLE "EmailDelivery" ADD COLUMN     "errorCode" TEXT,
ADD COLUMN     "leaseExpiresAt" TIMESTAMP(3),
ADD COLUMN     "leaseToken" TEXT,
ADD COLUMN     "messageId" TEXT NOT NULL,
ADD COLUMN     "nextAttemptAt" TIMESTAMP(3),
ADD COLUMN     "rankingRunId" TEXT NOT NULL,
ADD COLUMN     "templateVersion" TEXT NOT NULL,
ADD COLUMN     "updatedAt" TIMESTAMP(3) NOT NULL;

-- AlterTable
ALTER TABLE "JobPrediction" ADD COLUMN     "processingRunId" TEXT NOT NULL;

-- AlterTable
ALTER TABLE "ModelVersion" ADD COLUMN     "contentHash" TEXT NOT NULL;

-- AlterTable
ALTER TABLE "ProcessingRun" ADD COLUMN     "featureSchemaVersion" TEXT,
ADD COLUMN     "modelVersionId" TEXT,
ADD COLUMN     "profileVersionId" TEXT;

-- AlterTable
ALTER TABLE "TrainingExample" ADD COLUMN     "payloadHash" TEXT NOT NULL,
ADD COLUMN     "profileVersionId" TEXT NOT NULL;

-- CreateIndex
CREATE UNIQUE INDEX "EmailDelivery_messageId_key" ON "EmailDelivery"("messageId");

-- CreateIndex
CREATE INDEX "EmailDelivery_status_nextAttemptAt_createdAt_idx" ON "EmailDelivery"("status", "nextAttemptAt", "createdAt");

-- CreateIndex
CREATE INDEX "JobPrediction_processingRunId_rank_idx" ON "JobPrediction"("processingRunId", "rank");

-- CreateIndex
CREATE UNIQUE INDEX "JobPrediction_jobId_processingRunId_key" ON "JobPrediction"("jobId", "processingRunId");

-- CreateIndex
CREATE UNIQUE INDEX "ModelVersion_contentHash_key" ON "ModelVersion"("contentHash");

-- CreateIndex
CREATE UNIQUE INDEX "TrainingExample_jobId_profileVersionId_featureSchemaVersion_key" ON "TrainingExample"("jobId", "profileVersionId", "featureSchemaVersion");

-- AddForeignKey
ALTER TABLE "TrainingExample" ADD CONSTRAINT "TrainingExample_profileVersionId_fkey" FOREIGN KEY ("profileVersionId") REFERENCES "ProfileVersion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- Only one profile and one model may be active at a time. Prisma does not
-- currently represent partial indexes in schema.prisma, so these invariants
-- live in the migration intentionally.
CREATE UNIQUE INDEX "ProfileVersion_one_active_idx"
ON "ProfileVersion" ("active")
WHERE "active" = true;

CREATE UNIQUE INDEX "ModelVersion_one_active_idx"
ON "ModelVersion" ("active")
WHERE "active" = true;

-- Normalization and ranking work must retain the exact versions used to
-- prepare or score a batch.
ALTER TABLE "ProcessingRun"
ADD CONSTRAINT "ProcessingRun_version_pins_check"
CHECK (
  (
    "stage" = 'ranking'
    AND "profileVersionId" IS NOT NULL
    AND "modelVersionId" IS NOT NULL
    AND "featureSchemaVersion" IS NOT NULL
  )
  OR (
    "stage" = 'normalization'
    AND "profileVersionId" IS NOT NULL
    AND "featureSchemaVersion" IS NOT NULL
  )
  OR "stage" NOT IN ('ranking', 'normalization')
);

-- AddForeignKey
ALTER TABLE "JobPrediction" ADD CONSTRAINT "JobPrediction_processingRunId_fkey" FOREIGN KEY ("processingRunId") REFERENCES "ProcessingRun"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ProcessingRun" ADD CONSTRAINT "ProcessingRun_profileVersionId_fkey" FOREIGN KEY ("profileVersionId") REFERENCES "ProfileVersion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ProcessingRun" ADD CONSTRAINT "ProcessingRun_modelVersionId_fkey" FOREIGN KEY ("modelVersionId") REFERENCES "ModelVersion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EmailDelivery" ADD CONSTRAINT "EmailDelivery_rankingRunId_fkey" FOREIGN KEY ("rankingRunId") REFERENCES "ProcessingRun"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
