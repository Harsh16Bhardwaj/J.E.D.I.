-- Convert the existing delivery queue into a member-aware mail-event queue
-- without deleting legacy delivery history.
ALTER TYPE "EmailStatus" RENAME VALUE 'PENDING' TO 'UNTOUCHED';

ALTER TABLE "EmailRecipient"
ADD COLUMN "groupMemberId" TEXT;

-- Existing onboarded addresses are linked through the canonical login email.
UPDATE "EmailRecipient" AS recipient
SET "groupMemberId" = member."id"
FROM "User" AS account
JOIN "GroupMember" AS member ON member."userId" = account."id"
WHERE recipient."emailNormalized" = LOWER(TRIM(account."email"));

-- Preserve unmatched legacy rows and their history, but do not allow them to
-- enter the personalized queue until they belong to an onboarded member.
UPDATE "EmailRecipient"
SET "active" = false,
    "deletedAt" = COALESCE("deletedAt", CURRENT_TIMESTAMP)
WHERE "groupMemberId" IS NULL AND "active" = true;

CREATE UNIQUE INDEX "EmailRecipient_groupMemberId_key"
ON "EmailRecipient"("groupMemberId");

ALTER TABLE "EmailRecipient"
ADD CONSTRAINT "EmailRecipient_groupMemberId_fkey"
FOREIGN KEY ("groupMemberId") REFERENCES "GroupMember"("id")
ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "EmailDelivery"
ALTER COLUMN "payloadSnapshot" DROP NOT NULL,
ADD COLUMN "groupMemberId" TEXT,
ADD COLUMN "profileContentHash" TEXT,
ADD COLUMN "personalizedJobs" JSONB;

UPDATE "EmailDelivery" AS delivery
SET "groupMemberId" = recipient."groupMemberId"
FROM "EmailRecipient" AS recipient
WHERE delivery."recipientId" = recipient."id";

CREATE UNIQUE INDEX "EmailDelivery_batchId_rankingRunId_recipientId_key"
ON "EmailDelivery"("batchId", "rankingRunId", "recipientId");

ALTER TABLE "EmailDelivery"
ADD CONSTRAINT "EmailDelivery_groupMemberId_fkey"
FOREIGN KEY ("groupMemberId") REFERENCES "GroupMember"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
