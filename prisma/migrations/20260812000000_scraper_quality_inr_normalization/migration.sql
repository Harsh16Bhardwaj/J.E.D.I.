ALTER TYPE "ScrapeRunStatus" ADD VALUE IF NOT EXISTS 'NORMALIZING';
ALTER TYPE "ScrapeRunStatus" ADD VALUE IF NOT EXISTS 'NORMALIZATION_FAILED';

ALTER TABLE "Job"
  ADD COLUMN "salaryInrMin" DECIMAL(14,2),
  ADD COLUMN "salaryInrMax" DECIMAL(14,2),
  ADD COLUMN "salaryFxRate" DECIMAL(18,8),
  ADD COLUMN "salaryFxAsOf" TIMESTAMP(3),
  ADD COLUMN "salaryFxProvider" TEXT;

ALTER TABLE "PreparedJob"
  ADD COLUMN "normalizationPolicyVersion" TEXT NOT NULL DEFAULT 'legacy-v1';

ALTER TABLE "ProcessingRun"
  ADD COLUMN "normalizationPolicyVersion" TEXT;

ALTER TABLE "ScrapeRun"
  ADD COLUMN "freeRequestCount" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "brightDataFallbackCount" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "providerUsageReason" TEXT;

ALTER TABLE "ScrapeCandidate"
  ADD COLUMN "atsType" TEXT NOT NULL DEFAULT 'unknown',
  ADD COLUMN "geographyEligibility" TEXT NOT NULL DEFAULT 'INELIGIBLE',
  ADD COLUMN "sourceQualityValid" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN "qualityFailures" JSONB,
  ADD COLUMN "descriptionLength" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "dateEvidence" TEXT;
