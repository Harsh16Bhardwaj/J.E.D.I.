-- Extend the fixed application funnel before moving state into its own table.
ALTER TYPE "ApplicationStatus" ADD VALUE IF NOT EXISTS 'SCREENING';
ALTER TYPE "ApplicationStatus" ADD VALUE IF NOT EXISTS 'ACCEPTED';

CREATE TYPE "ApplicationMilestoneType" AS ENUM (
    'SCREENING',
    'ASSESSMENT',
    'INTERVIEW',
    'FOLLOW_UP',
    'OTHER'
);

CREATE TYPE "ApplicationMilestoneStatus" AS ENUM (
    'PLANNED',
    'COMPLETED',
    'CANCELLED'
);

CREATE TABLE "Application" (
    "jobId" TEXT NOT NULL,
    "status" "ApplicationStatus" NOT NULL DEFAULT 'NOT_STARTED',
    "appliedAt" TIMESTAMP(3),
    "targetApplyBy" TIMESTAMP(3),
    "nextAction" TEXT,
    "nextActionDueAt" TIMESTAMP(3),
    "portalUrl" TEXT,
    "referenceCode" TEXT,
    "notes" TEXT,
    "closedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Application_pkey" PRIMARY KEY ("jobId")
);

ALTER TABLE "Application"
ADD CONSTRAINT "Application_jobId_fkey"
FOREIGN KEY ("jobId") REFERENCES "Job"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

CREATE INDEX "Application_status_updatedAt_idx"
ON "Application"("status", "updatedAt");

CREATE INDEX "Application_nextActionDueAt_idx"
ON "Application"("nextActionDueAt");

-- Preserve every application that had progressed beyond the implicit default.
-- Existing notes stay on JobState because they were also used as review notes.
INSERT INTO "Application" (
    "jobId",
    "status",
    "appliedAt",
    "closedAt",
    "createdAt",
    "updatedAt"
)
SELECT
    state."jobId",
    state."applicationStatus",
    CASE
        WHEN state."applicationStatus" IN (
            'APPLIED', 'ASSESSMENT', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN'
        ) THEN COALESCE(
            (
                SELECT MIN(event."eventAt")
                FROM "JobEvent" AS event
                WHERE event."jobId" = state."jobId"
                  AND UPPER(event."eventType") = 'APPLIED'
            ),
            state."updatedAt"
        )
        ELSE NULL
    END,
    CASE
        WHEN state."applicationStatus" IN ('REJECTED', 'WITHDRAWN')
        THEN COALESCE(
            (
                SELECT MAX(event."eventAt")
                FROM "JobEvent" AS event
                WHERE event."jobId" = state."jobId"
                  AND UPPER(event."eventType") = state."applicationStatus"::text
            ),
            state."updatedAt"
        )
        ELSE NULL
    END,
    state."updatedAt",
    state."updatedAt"
FROM "JobState" AS state
WHERE state."applicationStatus" <> 'NOT_STARTED';

ALTER TABLE "JobEvent"
ADD COLUMN "previousStatus" "ApplicationStatus",
ADD COLUMN "newStatus" "ApplicationStatus";

-- Old events stored the destination stage in eventType. Reconstruct the
-- previous/new pair in chronological order while keeping eventType untouched.
WITH recognized_events AS (
    SELECT
        event."id",
        event."jobId",
        event."eventAt",
        event."createdAt",
        CASE
            WHEN UPPER(event."eventType") IN (
                'NOT_STARTED', 'PREPARING', 'APPLIED', 'ASSESSMENT',
                'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN'
            ) THEN UPPER(event."eventType")
            ELSE NULL
        END AS new_status
    FROM "JobEvent" AS event
), ordered_events AS (
    SELECT
        recognized."id",
        recognized.new_status,
        LAG(recognized.new_status) OVER (
            PARTITION BY recognized."jobId"
            ORDER BY recognized."eventAt", recognized."createdAt", recognized."id"
        ) AS previous_status
    FROM recognized_events AS recognized
    WHERE recognized.new_status IS NOT NULL
)
UPDATE "JobEvent" AS event
SET
    "previousStatus" = COALESCE(ordered.previous_status, 'NOT_STARTED')::"ApplicationStatus",
    "newStatus" = ordered.new_status::"ApplicationStatus"
FROM ordered_events AS ordered
WHERE event."id" = ordered."id";

ALTER TABLE "JobState" DROP COLUMN "applicationStatus";

CREATE TABLE "ApplicationMilestone" (
    "id" TEXT NOT NULL,
    "applicationJobId" TEXT NOT NULL,
    "type" "ApplicationMilestoneType" NOT NULL,
    "title" TEXT NOT NULL,
    "status" "ApplicationMilestoneStatus" NOT NULL DEFAULT 'PLANNED',
    "scheduledAt" TIMESTAMP(3),
    "completedAt" TIMESTAMP(3),
    "notes" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ApplicationMilestone_pkey" PRIMARY KEY ("id")
);

ALTER TABLE "ApplicationMilestone"
ADD CONSTRAINT "ApplicationMilestone_applicationJobId_fkey"
FOREIGN KEY ("applicationJobId") REFERENCES "Application"("jobId")
ON DELETE CASCADE ON UPDATE CASCADE;

CREATE INDEX "ApplicationMilestone_applicationJobId_scheduledAt_idx"
ON "ApplicationMilestone"("applicationJobId", "scheduledAt");
