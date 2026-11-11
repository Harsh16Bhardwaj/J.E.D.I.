import assert from "node:assert/strict";
import test from "node:test";

import {
  allNavigation,
  adminNavigation,
  isAdminRoute,
  currentNavigation,
  searchNavigation,
  settingsNavigation,
  visibleNavigation,
} from "./navigation";
import {
  completeTutorialChapter,
  completedTutorialChapters,
  hasCompletedTutorial,
  persistTutorialComplete,
  TUTORIAL_COMPLETE_KEY,
} from "./tutorial-state";

test("chapter progress preserves the legacy core guide without completing new guides", () => {
  const values = new Map([[TUTORIAL_COMPLETE_KEY, "1"]]);
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
  };
  assert.deepEqual([...completedTutorialChapters(storage)], ["core-guide"]);
  completeTutorialChapter(storage, "job-intake");
  completeTutorialChapter(storage, "job-intake");
  assert.deepEqual(
    [...completedTutorialChapters(storage)],
    ["core-guide", "job-intake"],
  );
});

test("members see everyday tools without admin navigation", () => {
  assert.deepEqual(
    visibleNavigation(allNavigation, { isGroupOwner: false }).map(
      (item) => item.label,
    ),
    [
      "Daily Feed",
      "Personal feed",
      "Jobs",
      "Resume fit",
      "Applications",
      "Learning",
      "Tutorial",
      "Group",
      "Shared leaderboard",
    ],
  );
  assert.deepEqual(
    visibleNavigation(adminNavigation, { isGroupOwner: false }),
    [],
  );
});

test("owners see scraper and batches together under Admin", () => {
  assert.deepEqual(
    adminNavigation.map((item) => item.label),
    ["Scraper", "Batches"],
  );
  assert.ok(adminNavigation.every((item) => item.ownerOnly));
  assert.equal(
    visibleNavigation(adminNavigation, { isGroupOwner: true }).length,
    2,
  );
  assert.deepEqual(
    visibleNavigation(settingsNavigation, { isGroupOwner: false }).map(
      (item) => item.label,
    ),
    ["Group"],
  );
});

test("admin routes include nested pages and exclude similarly named paths", () => {
  for (const path of [
    "/batches",
    "/batches/example",
    "/scraper",
    "/scraper/run",
  ])
    assert.equal(isAdminRoute(path), true);
  for (const path of ["/jobs", "/batches-other", "/scrapers", "/dashboard"])
    assert.equal(isAdminRoute(path), false);
});

test("the tutorial remains new until completion is explicitly persisted", () => {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
  };

  assert.equal(hasCompletedTutorial(storage), false);
  persistTutorialComplete(storage);
  assert.equal(values.get(TUTORIAL_COMPLETE_KEY), "1");
  assert.equal(hasCompletedTutorial(storage), true);
  persistTutorialComplete(storage);
  assert.equal(hasCompletedTutorial(storage), true);
});

test("the most specific route owns the active navigation state", () => {
  assert.equal(currentNavigation("/jobs/intake")?.href, "/jobs/intake");
  assert.equal(currentNavigation("/jobs/some-job")?.href, "/jobs");
  assert.equal(currentNavigation("/jobs-other"), undefined);
  assert.equal(currentNavigation("/settings/models")?.label, "Models");
});

test("page search respects role access and matches every query word", () => {
  const member = { isGroupOwner: false };
  assert.equal(searchNavigation("scraper", member).length, 0);
  assert.equal(searchNavigation("models", member).length, 0);
  assert.equal(
    searchNavigation("  RESUME fit  ", member)[0]?.href,
    "/jobs/intake",
  );
  assert.equal(searchNavigation("no such place", member).length, 0);
  assert.equal(
    searchNavigation("scraper", { isGroupOwner: true })[0]?.href,
    "/scraper",
  );
  assert.equal(
    searchNavigation("", member).length,
    visibleNavigation(allNavigation, member).length,
  );
});
