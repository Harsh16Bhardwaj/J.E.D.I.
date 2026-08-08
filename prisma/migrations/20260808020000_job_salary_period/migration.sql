CREATE TYPE "SalaryPeriod" AS ENUM ('YEARLY', 'MONTHLY');

ALTER TABLE "Job" ADD COLUMN "salaryPeriod" "SalaryPeriod";

UPDATE "Job"
SET "salaryPeriod" = 'YEARLY'
WHERE "salaryMin" IS NOT NULL OR "salaryMax" IS NOT NULL;
