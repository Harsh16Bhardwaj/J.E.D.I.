CREATE TABLE "RecommendationBatch" (
 "id" TEXT PRIMARY KEY,
 "status" TEXT NOT NULL CHECK ("status" IN ('READY', 'FAILED')),
 "pools" JSONB NOT NULL,
 "catalogCount" INTEGER NOT NULL DEFAULT 0,
 "truncated" BOOLEAN NOT NULL DEFAULT false,
 "errorCode" TEXT,
 "createdAt" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
 "completedAt" TIMESTAMPTZ(3)
);
ALTER TABLE "RecommendationBatch" ENABLE ROW LEVEL SECURITY;
