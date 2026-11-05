CREATE TABLE "JobDraft" (
  "groupMemberId" TEXT NOT NULL,
  "id" TEXT NOT NULL,
  "description" TEXT NOT NULL,
  "preview" JSONB NOT NULL,
  "revision" INTEGER NOT NULL DEFAULT 1,
  "updatedAt" TIMESTAMPTZ(3) NOT NULL,
  CONSTRAINT "JobDraft_pkey" PRIMARY KEY ("groupMemberId", "id"),
  CONSTRAINT "JobDraft_groupMemberId_fkey" FOREIGN KEY ("groupMemberId")
    REFERENCES "GroupMember"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX "JobDraft_groupMemberId_updatedAt_idx"
  ON "JobDraft"("groupMemberId", "updatedAt");

ALTER TABLE "JobDraft" ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE "JobDraft" FROM anon, authenticated;
