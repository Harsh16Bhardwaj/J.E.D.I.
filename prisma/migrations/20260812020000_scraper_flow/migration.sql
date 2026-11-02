ALTER TABLE "ScrapeRun"
ADD COLUMN "sourceCount" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN "processedSourceCount" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN "stoppedEarly" BOOLEAN NOT NULL DEFAULT false;

UPDATE "ScrapeRun" AS run
SET
  "sourceCount" = counts.total_count,
  "processedSourceCount" = counts.processed_count
FROM (
  SELECT
    "runId",
    COUNT(*)::INTEGER AS total_count,
    COUNT(*) FILTER (WHERE status IN ('SUCCEEDED', 'FAILED'))::INTEGER AS processed_count
  FROM "ScrapeAttempt"
  GROUP BY "runId"
) AS counts
WHERE run.id = counts."runId";
