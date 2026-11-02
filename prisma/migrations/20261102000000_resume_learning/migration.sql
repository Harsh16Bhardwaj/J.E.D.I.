-- Add member-private resume evidence and timed learning attempts.
-- No existing table data or column definitions are changed.
-- Apply atomically and fail quickly rather than waiting on a busy table.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

-- CreateTable
CREATE TABLE "public"."ResumeEvidence" (
    "id" TEXT NOT NULL,
    "groupMemberId" TEXT NOT NULL,
    "evidence" JSONB NOT NULL,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ResumeEvidence_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "public"."LearningAttempt" (
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

    CONSTRAINT "LearningAttempt_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "ResumeEvidence_groupMemberId_key" ON "public"."ResumeEvidence"("groupMemberId");

-- CreateIndex
CREATE INDEX "LearningAttempt_groupMemberId_startedAt_idx" ON "public"."LearningAttempt"("groupMemberId", "startedAt");

-- AddForeignKey
ALTER TABLE "public"."ResumeEvidence" ADD CONSTRAINT "ResumeEvidence_groupMemberId_fkey" FOREIGN KEY ("groupMemberId") REFERENCES "public"."GroupMember"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "public"."LearningAttempt" ADD CONSTRAINT "LearningAttempt_groupMemberId_fkey" FOREIGN KEY ("groupMemberId") REFERENCES "public"."GroupMember"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Preserve the backend-only Supabase boundary for these new objects.
ALTER TABLE "public"."ResumeEvidence" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."LearningAttempt" ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE
    "public"."ResumeEvidence", "public"."LearningAttempt" FROM PUBLIC;

-- Plain PostgreSQL development databases may not have Supabase API roles.
DO $$
DECLARE api_role TEXT;
BEGIN
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON TABLE public."ResumeEvidence", '
                'public."LearningAttempt" FROM %I', api_role
            );
        END IF;
    END LOOP;
END
$$;

COMMIT;
