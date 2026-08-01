-- Create the single shared JEDI workspace without changing the User table.
CREATE TABLE "Group" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL DEFAULT 'JEDI',
    "ownerId" TEXT NOT NULL,
    "activeProfileVersionId" TEXT,
    "activeModelVersionId" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Group_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "Group_ownerId_key"
ON "Group"("ownerId");

CREATE INDEX "Group_activeProfileVersionId_idx"
ON "Group"("activeProfileVersionId");

CREATE INDEX "Group_activeModelVersionId_idx"
ON "Group"("activeModelVersionId");

ALTER TABLE "Group"
ADD CONSTRAINT "Group_ownerId_fkey"
FOREIGN KEY ("ownerId") REFERENCES "User"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;

ALTER TABLE "Group"
ADD CONSTRAINT "Group_activeProfileVersionId_fkey"
FOREIGN KEY ("activeProfileVersionId") REFERENCES "ProfileVersion"("id")
ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "Group"
ADD CONSTRAINT "Group_activeModelVersionId_fkey"
FOREIGN KEY ("activeModelVersionId") REFERENCES "ModelVersion"("id")
ON DELETE SET NULL ON UPDATE CASCADE;

CREATE TABLE "GroupMember" (
    "id" TEXT NOT NULL,
    "groupId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "onboardingCompletedAt" TIMESTAMP(3),
    "joinedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "GroupMember_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "GroupMember_userId_key"
ON "GroupMember"("userId");

CREATE UNIQUE INDEX "GroupMember_groupId_userId_key"
ON "GroupMember"("groupId", "userId");

CREATE INDEX "GroupMember_groupId_joinedAt_idx"
ON "GroupMember"("groupId", "joinedAt");

ALTER TABLE "GroupMember"
ADD CONSTRAINT "GroupMember_groupId_fkey"
FOREIGN KEY ("groupId") REFERENCES "Group"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "GroupMember"
ADD CONSTRAINT "GroupMember_userId_fkey"
FOREIGN KEY ("userId") REFERENCES "User"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "GroupInvitation" (
    "id" TEXT NOT NULL,
    "groupId" TEXT NOT NULL,
    "codeHash" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    "revokedAt" TIMESTAMP(3),
    "usageCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "GroupInvitation_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "GroupInvitation_codeHash_key"
ON "GroupInvitation"("codeHash");

CREATE INDEX "GroupInvitation_groupId_revokedAt_expiresAt_idx"
ON "GroupInvitation"("groupId", "revokedAt", "expiresAt");

ALTER TABLE "GroupInvitation"
ADD CONSTRAINT "GroupInvitation_groupId_fkey"
FOREIGN KEY ("groupId") REFERENCES "Group"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "MemberProfile" (
    "id" TEXT NOT NULL,
    "groupMemberId" TEXT NOT NULL,
    "contentHash" TEXT NOT NULL,
    "resumeText" TEXT NOT NULL,
    "preferredTitles" TEXT[],
    "preferredLocations" TEXT[],
    "preferredSkills" TEXT[],
    "experienceMinYears" DOUBLE PRECISION,
    "experienceMaxYears" DOUBLE PRECISION,
    "salaryMin" DECIMAL(14,2),
    "salaryMax" DECIMAL(14,2),
    "salaryCurrency" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "MemberProfile_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "MemberProfile_groupMemberId_key"
ON "MemberProfile"("groupMemberId");

CREATE INDEX "MemberProfile_contentHash_idx"
ON "MemberProfile"("contentHash");

ALTER TABLE "MemberProfile"
ADD CONSTRAINT "MemberProfile_groupMemberId_fkey"
FOREIGN KEY ("groupMemberId") REFERENCES "GroupMember"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

-- Turn the earliest existing account into the owner of the default group. The
-- currently active global profile and model become that group's shared v1 pins.
INSERT INTO "Group" (
    "id",
    "name",
    "ownerId",
    "activeProfileVersionId",
    "activeModelVersionId",
    "createdAt",
    "updatedAt"
)
SELECT
    'jedi-default-group',
    'JEDI',
    owner."id",
    (
        SELECT "id" FROM "ProfileVersion"
        WHERE "active" = true
        ORDER BY "createdAt" DESC, "id" ASC
        LIMIT 1
    ),
    (
        SELECT "id" FROM "ModelVersion"
        WHERE "active" = true
        ORDER BY "createdAt" DESC, "id" ASC
        LIMIT 1
    ),
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM (
    SELECT "id" FROM "User"
    ORDER BY "createdAt" ASC, "id" ASC
    LIMIT 1
) AS owner;

-- Existing accounts retain access. The owner is already onboarded; any
-- unexpected additional legacy accounts will complete onboarding after login.
INSERT INTO "GroupMember" (
    "id",
    "groupId",
    "userId",
    "onboardingCompletedAt",
    "joinedAt"
)
SELECT
    'jedi-member-' || md5(member."id"),
    shared_group."id",
    member."id",
    CASE
        WHEN member."id" = shared_group."ownerId" THEN CURRENT_TIMESTAMP
        ELSE NULL
    END,
    CURRENT_TIMESTAMP
FROM "User" AS member
CROSS JOIN "Group" AS shared_group
WHERE shared_group."id" = 'jedi-default-group';

-- Preserve the owner's current preferences as their future-personalization
-- profile as well as the group's active ranking profile.
INSERT INTO "MemberProfile" (
    "id",
    "groupMemberId",
    "contentHash",
    "resumeText",
    "preferredTitles",
    "preferredLocations",
    "preferredSkills",
    "experienceMinYears",
    "experienceMaxYears",
    "salaryMin",
    "salaryMax",
    "salaryCurrency",
    "createdAt",
    "updatedAt"
)
SELECT
    'jedi-profile-' || md5(membership."id"),
    membership."id",
    profile."contentHash",
    profile."resumeText",
    profile."preferredTitles",
    profile."preferredLocations",
    profile."preferredSkills",
    profile."experienceMinYears",
    profile."experienceMaxYears",
    profile."salaryMin",
    profile."salaryMax",
    profile."salaryCurrency",
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM "Group" AS shared_group
JOIN "GroupMember" AS membership
    ON membership."userId" = shared_group."ownerId"
JOIN "ProfileVersion" AS profile
    ON profile."id" = shared_group."activeProfileVersionId"
WHERE shared_group."id" = 'jedi-default-group';
