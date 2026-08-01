-- Friendly labels are presentation-only. externalBatchId remains the immutable import key.
ALTER TABLE "Batch" ADD COLUMN "displayName" TEXT;

WITH ordered AS (
  SELECT
    id,
    ROW_NUMBER() OVER (ORDER BY "createdAt", id) - 1 AS position
  FROM "Batch"
), names AS (
  SELECT
    id,
    (ARRAY[
      'Agile','Bright','Bold','Brave','Calm','Candid','Capable','Clever','Curious','Daring',
      'Earnest','Eager','Focused','Gallant','Gentle','Golden','Grounded','Happy','Hardy','Helpful',
      'Honest','Keen','Kind','Lively','Loyal','Lucid','Mighty','Nimble','Noble','Patient','Plucky',
      'Polished','Quick','Radiant','Ready','Resolute','Sharp','Steady','Stellar','Sunny','Swift',
      'Thoughtful','True','Valiant','Vibrant','Warm','Wise','Witty','Zesty','Zealous'
    ])[(((position / 5000) % 50) + 1)::INT] || ' ' ||
    (ARRAY[
      'Badger','Beacon','Bear','Bee','Bison','Comet','Condor','Crane','Dolphin','Eagle',
      'Falcon','Finch','Fox','Gazelle','Harbor','Heron','Horizon','Jaguar','Kestrel','Koala',
      'Lantern','Leopard','Lion','Lynx','Maple','Meadow','Meteor','Narwhal','Orca','Otter',
      'Owl','Panda','Panther','Pine','Puffin','Quill','Raven','River','Robin','Sequoia',
      'Sparrow','Summit','Swan','Tiger','Toucan','Voyager','Willow','Wolf','Wren','Yak'
    ])[(((position / 100) % 50) + 1)::INT] || ' ' ||
    LPAD((position % 100)::TEXT, 2, '0') AS "displayName"
  FROM ordered
)
UPDATE "Batch" AS batch
SET "displayName" = names."displayName"
FROM names
WHERE batch.id = names.id;

CREATE UNIQUE INDEX "Batch_displayName_key" ON "Batch"("displayName");
