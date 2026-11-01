import assert from "node:assert/strict";
import test from "node:test";
import {
  remainingSeconds,
  sprintSettings,
  nextQuestionIndex,
} from "./learning";

test("timer uses a deadline and accounts for server clock offset", () => {
  assert.equal(
    remainingSeconds(
      "2026-11-01T10:01:00Z",
      Date.parse("2026-11-01T10:00:01Z"),
      0,
    ),
    59,
  );
  assert.equal(
    remainingSeconds(
      "2026-11-01T10:01:00Z",
      Date.parse("2026-11-01T10:02:00Z"),
      0,
    ),
    0,
  );
  assert.equal(
    remainingSeconds(
      "2026-11-01T10:01:00Z",
      Date.parse("2026-11-01T10:00:01Z"),
      10000,
    ),
    49,
  );
});

test("sprint settings reject unavailable counts and invalid duration", () => {
  assert.equal(sprintSettings(4, 60, 3), false);
  assert.equal(sprintSettings(1, 29, 3), false);
  assert.equal(sprintSettings(1.5, 60, 3), false);
  assert.equal(sprintSettings(3, 60, 3), true);
});

test("resume opens at the first unanswered question", () => {
  assert.equal(
    nextQuestionIndex([{ selectedOptionId: "b" }, { selectedOptionId: null }]),
    1,
  );
  assert.equal(nextQuestionIndex([{ selectedOptionId: "b" }]), 0);
});
