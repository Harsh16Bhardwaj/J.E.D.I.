-- Existing activity predates multi-member state and therefore belongs to the
-- default group's owner. New writes are scoped to the authenticated membership.

BEGIN;

ALTER TABLE "JobState"
ADD COLUMN "groupMemberId" TEXT,
ADD COLUMN "viewedAt" TIMESTAMP(3);

UPDATE "JobState" AS state
SET
    "groupMemberId" = owner_membership."id",
    "viewedAt" = CASE
        WHEN state."reviewStatus" <> 'NEW' THEN state."updatedAt"
        ELSE NULL
    END
FROM (
    SELECT membership."id"
    FROM "GroupMember" AS membership
    JOIN "Group" AS shared_group ON shared_group."id" = membership."groupId"
    WHERE membership."userId" = shared_group."ownerId"
    ORDER BY membership."joinedAt", membership."id"
    LIMIT 1
) AS owner_membership;

ALTER TABLE "JobState" DROP CONSTRAINT "JobState_pkey";
ALTER TABLE "JobState" ALTER COLUMN "groupMemberId" SET NOT NULL;
ALTER TABLE "JobState"
ADD CONSTRAINT "JobState_pkey" PRIMARY KEY ("groupMemberId", "jobId");
ALTER TABLE "JobState"
ADD CONSTRAINT "JobState_groupMemberId_fkey"
FOREIGN KEY ("groupMemberId") REFERENCES "GroupMember"("id")
ON DELETE CASCADE ON UPDATE CASCADE;
CREATE INDEX "JobState_jobId_idx" ON "JobState"("jobId");
CREATE INDEX "JobState_groupMemberId_reviewStatus_idx"
ON "JobState"("groupMemberId", "reviewStatus");
CREATE INDEX "JobState_groupMemberId_viewedAt_idx"
ON "JobState"("groupMemberId", "viewedAt");

ALTER TABLE "JobAnnotation" ADD COLUMN "groupMemberId" TEXT;
UPDATE "JobAnnotation"
SET "groupMemberId" = owner_membership."id"
FROM (
    SELECT membership."id"
    FROM "GroupMember" AS membership
    JOIN "Group" AS shared_group ON shared_group."id" = membership."groupId"
    WHERE membership."userId" = shared_group."ownerId"
    ORDER BY membership."joinedAt", membership."id"
    LIMIT 1
) AS owner_membership;
ALTER TABLE "JobAnnotation" DROP CONSTRAINT "JobAnnotation_pkey";
ALTER TABLE "JobAnnotation" ALTER COLUMN "groupMemberId" SET NOT NULL;
ALTER TABLE "JobAnnotation"
ADD CONSTRAINT "JobAnnotation_pkey" PRIMARY KEY ("groupMemberId", "jobId");
ALTER TABLE "JobAnnotation"
ADD CONSTRAINT "JobAnnotation_groupMemberId_fkey"
FOREIGN KEY ("groupMemberId") REFERENCES "GroupMember"("id")
ON DELETE CASCADE ON UPDATE CASCADE;
CREATE INDEX "JobAnnotation_jobId_idx" ON "JobAnnotation"("jobId");

ALTER TABLE "Application"
ADD COLUMN "id" TEXT,
ADD COLUMN "groupMemberId" TEXT;
UPDATE "Application" AS application
SET
    "id" = 'app-' || md5(application."jobId" || owner_membership."id"),
    "groupMemberId" = owner_membership."id"
FROM (
    SELECT membership."id"
    FROM "GroupMember" AS membership
    JOIN "Group" AS shared_group ON shared_group."id" = membership."groupId"
    WHERE membership."userId" = shared_group."ownerId"
    ORDER BY membership."joinedAt", membership."id"
    LIMIT 1
) AS owner_membership;
ALTER TABLE "ApplicationMilestone" ADD COLUMN "applicationId" TEXT;
UPDATE "ApplicationMilestone" AS milestone
SET "applicationId" = application."id"
FROM "Application" AS application
WHERE application."jobId" = milestone."applicationJobId";
ALTER TABLE "ApplicationMilestone"
DROP CONSTRAINT "ApplicationMilestone_applicationJobId_fkey";
DROP INDEX "ApplicationMilestone_applicationJobId_scheduledAt_idx";
ALTER TABLE "ApplicationMilestone" ALTER COLUMN "applicationId" SET NOT NULL;
ALTER TABLE "ApplicationMilestone" DROP COLUMN "applicationJobId";

ALTER TABLE "JobEvent" ADD COLUMN "applicationId" TEXT;
UPDATE "JobEvent" AS event
SET "applicationId" = application."id"
FROM "Application" AS application
WHERE application."jobId" = event."jobId";
ALTER TABLE "JobEvent" DROP CONSTRAINT "JobEvent_jobId_fkey";
DROP INDEX "JobEvent_jobId_eventAt_idx";
ALTER TABLE "JobEvent" ALTER COLUMN "applicationId" SET NOT NULL;
ALTER TABLE "JobEvent" DROP COLUMN "jobId";
ALTER TABLE "JobEvent" RENAME TO "ApplicationEvent";

-- The old dependent foreign keys are now detached, so the application key can
-- safely change from the shared job id to the private application id.
ALTER TABLE "Application" DROP CONSTRAINT "Application_pkey";
DROP INDEX "Application_status_updatedAt_idx";
DROP INDEX "Application_nextActionDueAt_idx";
ALTER TABLE "Application" ALTER COLUMN "id" SET NOT NULL;
ALTER TABLE "Application" ALTER COLUMN "groupMemberId" SET NOT NULL;
ALTER TABLE "Application"
ADD CONSTRAINT "Application_pkey" PRIMARY KEY ("id");
ALTER TABLE "Application"
ADD CONSTRAINT "Application_groupMemberId_fkey"
FOREIGN KEY ("groupMemberId") REFERENCES "GroupMember"("id")
ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Application"
ADD CONSTRAINT "Application_groupMemberId_jobId_key"
UNIQUE ("groupMemberId", "jobId");
CREATE INDEX "Application_jobId_idx" ON "Application"("jobId");
CREATE INDEX "Application_groupMemberId_status_updatedAt_idx"
ON "Application"("groupMemberId", "status", "updatedAt");
CREATE INDEX "Application_groupMemberId_nextActionDueAt_idx"
ON "Application"("groupMemberId", "nextActionDueAt");

ALTER TABLE "ApplicationMilestone"
ADD CONSTRAINT "ApplicationMilestone_applicationId_fkey"
FOREIGN KEY ("applicationId") REFERENCES "Application"("id")
ON DELETE CASCADE ON UPDATE CASCADE;
CREATE INDEX "ApplicationMilestone_applicationId_scheduledAt_idx"
ON "ApplicationMilestone"("applicationId", "scheduledAt");

ALTER TABLE "ApplicationEvent"
ADD CONSTRAINT "ApplicationEvent_applicationId_fkey"
FOREIGN KEY ("applicationId") REFERENCES "Application"("id")
ON DELETE CASCADE ON UPDATE CASCADE;
CREATE INDEX "ApplicationEvent_applicationId_eventAt_idx"
ON "ApplicationEvent"("applicationId", "eventAt");

ALTER TABLE "TrainingExample" ADD COLUMN "annotatedByGroupMemberId" TEXT;
UPDATE "TrainingExample"
SET "annotatedByGroupMemberId" = owner_membership."id"
FROM (
    SELECT membership."id"
    FROM "GroupMember" AS membership
    JOIN "Group" AS shared_group ON shared_group."id" = membership."groupId"
    WHERE membership."userId" = shared_group."ownerId"
    ORDER BY membership."joinedAt", membership."id"
    LIMIT 1
) AS owner_membership;
ALTER TABLE "TrainingExample"
ALTER COLUMN "annotatedByGroupMemberId" SET NOT NULL;
ALTER TABLE "TrainingExample"
ADD CONSTRAINT "TrainingExample_annotatedByGroupMemberId_fkey"
FOREIGN KEY ("annotatedByGroupMemberId") REFERENCES "GroupMember"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
CREATE INDEX "TrainingExample_annotatedByGroupMemberId_idx"
ON "TrainingExample"("annotatedByGroupMemberId");

COMMIT;
