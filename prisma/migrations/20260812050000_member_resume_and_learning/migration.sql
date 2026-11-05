-- These models were added to the schema before their migration was checked in.
-- Preserve data on databases where the schema was already pushed.
CREATE TABLE IF NOT EXISTS "ResumeEvidence" (
  "id" TEXT NOT NULL,
  "groupMemberId" TEXT NOT NULL,
  "evidence" JSONB NOT NULL,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "ResumeEvidence_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "ResumeEvidence_groupMemberId_fkey" FOREIGN KEY ("groupMemberId")
    REFERENCES "GroupMember"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS "ResumeEvidence_groupMemberId_key"
  ON "ResumeEvidence"("groupMemberId");

CREATE TABLE IF NOT EXISTS "LearningAttempt" (
  "id" TEXT NOT NULL,
  "groupMemberId" TEXT NOT NULL,
  "topicId" TEXT NOT NULL,
  "jobId" TEXT,
  "snapshot" JSONB NOT NULL,
  "answers" JSONB NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'ACTIVE',
  "revision" INTEGER NOT NULL DEFAULT 0,
  "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "deadlineAt" TIMESTAMP(3) NOT NULL,
  "finishedAt" TIMESTAMP(3),
  CONSTRAINT "LearningAttempt_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "LearningAttempt_groupMemberId_fkey" FOREIGN KEY ("groupMemberId")
    REFERENCES "GroupMember"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS "LearningAttempt_groupMemberId_startedAt_idx"
  ON "LearningAttempt"("groupMemberId", "startedAt");

ALTER TABLE "ResumeEvidence" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "LearningAttempt" ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE "ResumeEvidence", "LearningAttempt"
  FROM anon, authenticated;
