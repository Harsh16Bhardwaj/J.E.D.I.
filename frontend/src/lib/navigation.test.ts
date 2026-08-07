import assert from "node:assert/strict";
import test from "node:test";

import {
  allNavigation,
  settingsNavigation,
  visibleNavigation,
} from "./navigation";
import {
  hasCompletedTutorial,
  persistTutorialComplete,
  TUTORIAL_COMPLETE_KEY,
} from "./tutorial-state";

test("members see the shared daily workflow without owner controls", () => {
  assert.deepEqual(
    visibleNavigation(allNavigation, { isGroupOwner: false }).map(({ label }) => label),
    ["Daily Feed", "Jobs", "Applications", "Tutorial", "Batches", "Group", "Email"],
  );
});

test("owners see shared profile, model, and training controls", () => {
  assert.deepEqual(
    visibleNavigation(allNavigation, { isGroupOwner: true }).map(({ label }) => label),
    [
      "Daily Feed",
      "Jobs",
      "Applications",
      "Tutorial",
      "Batches",
      "Group",
      "Email",
      "Shared Profile",
      "Models",
      "Training Data",
    ],
  );
  assert.deepEqual(
    visibleNavigation(settingsNavigation, { isGroupOwner: false }).map(({ label }) => label),
    ["Group", "Email"],
  );
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
