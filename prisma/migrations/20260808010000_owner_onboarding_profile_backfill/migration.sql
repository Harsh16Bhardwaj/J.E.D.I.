-- Early fresh-database owner registration saved MemberProfile data but did not
-- initialize the shared ProfileVersion required by normalization. Backfill the
-- single v1 group from its owner's completed onboarding profile.
WITH target AS (
    SELECT
        shared_group."id" AS "groupId",
        member_profile.*
    FROM "Group" AS shared_group
    JOIN "GroupMember" AS owner_membership
      ON owner_membership."groupId" = shared_group."id"
     AND owner_membership."userId" = shared_group."ownerId"
    JOIN "MemberProfile" AS member_profile
      ON member_profile."groupMemberId" = owner_membership."id"
    WHERE shared_group."activeProfileVersionId" IS NULL
    ORDER BY shared_group."createdAt" ASC
    LIMIT 1
)
INSERT INTO "ProfileVersion" (
    "id",
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
    "active",
    "createdAt"
)
SELECT
    'owner-profile-' || substring(md5(target."id" || target."contentHash"), 1, 20),
    target."contentHash",
    target."resumeText",
    target."preferredTitles",
    target."preferredLocations",
    target."preferredSkills",
    target."experienceMinYears",
    target."experienceMaxYears",
    target."salaryMin",
    target."salaryMax",
    target."salaryCurrency",
    false,
    target."createdAt"
FROM target
ON CONFLICT ("contentHash") DO NOTHING;

WITH target AS (
    SELECT profile."id" AS "profileId", shared_group."id" AS "groupId"
    FROM "Group" AS shared_group
    JOIN "GroupMember" AS owner_membership
      ON owner_membership."groupId" = shared_group."id"
     AND owner_membership."userId" = shared_group."ownerId"
    JOIN "MemberProfile" AS member_profile
      ON member_profile."groupMemberId" = owner_membership."id"
    JOIN "ProfileVersion" AS profile
      ON profile."contentHash" = member_profile."contentHash"
    WHERE shared_group."activeProfileVersionId" IS NULL
    ORDER BY shared_group."createdAt" ASC
    LIMIT 1
)
UPDATE "ProfileVersion"
SET "active" = false
WHERE "active" = true
  AND EXISTS (SELECT 1 FROM target);

WITH target AS (
    SELECT profile."id" AS "profileId", shared_group."id" AS "groupId"
    FROM "Group" AS shared_group
    JOIN "GroupMember" AS owner_membership
      ON owner_membership."groupId" = shared_group."id"
     AND owner_membership."userId" = shared_group."ownerId"
    JOIN "MemberProfile" AS member_profile
      ON member_profile."groupMemberId" = owner_membership."id"
    JOIN "ProfileVersion" AS profile
      ON profile."contentHash" = member_profile."contentHash"
    WHERE shared_group."activeProfileVersionId" IS NULL
    ORDER BY shared_group."createdAt" ASC
    LIMIT 1
)
UPDATE "ProfileVersion" AS profile
SET "active" = true
FROM target
WHERE profile."id" = target."profileId";

WITH target AS (
    SELECT profile."id" AS "profileId", shared_group."id" AS "groupId"
    FROM "Group" AS shared_group
    JOIN "GroupMember" AS owner_membership
      ON owner_membership."groupId" = shared_group."id"
     AND owner_membership."userId" = shared_group."ownerId"
    JOIN "MemberProfile" AS member_profile
      ON member_profile."groupMemberId" = owner_membership."id"
    JOIN "ProfileVersion" AS profile
      ON profile."contentHash" = member_profile."contentHash"
    WHERE shared_group."activeProfileVersionId" IS NULL
    ORDER BY shared_group."createdAt" ASC
    LIMIT 1
)
UPDATE "Group" AS shared_group
SET "activeProfileVersionId" = target."profileId",
    "updatedAt" = CURRENT_TIMESTAMP
FROM target
WHERE shared_group."id" = target."groupId";
