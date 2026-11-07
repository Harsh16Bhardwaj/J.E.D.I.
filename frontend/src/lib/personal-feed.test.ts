import assert from "node:assert/strict";
import test from "node:test";
import { parsePreferences, feedStates } from "./personal-feed";

function form(values: Record<string, string>) {
  const data = new FormData();
  Object.entries(values).forEach(([key, value]) => data.set(key, value));
  return data;
}

test("personal preferences preserve unspecified numbers and normalize lists", () => {
  const result = parsePreferences(
    form({
      titles: "Engineer, Designer, Engineer",
      skills: "React.js",
      currency: "usd",
    }),
  );
  assert.deepEqual(result.preferredTitles, ["Engineer", "Designer"]);
  assert.equal(result.experienceMaxYears, null);
  assert.equal(result.salaryMin, null);
  assert.equal(result.salaryCurrency, "USD");
});

test("personal preferences reject missing direction, invalid numbers, and reversed ranges", () => {
  const invalid: Record<string, string>[] = [
    {},
    { skills: "React", salaryMin: "NaN" },
    { skills: "React", experienceMax: "-1" },
    { skills: "React", experienceMin: "4", experienceMax: "2" },
    { skills: "React", salaryMin: "10", salaryMax: "2" },
    { titles: "Developer", experienceMin: "81" },
  ];
  for (const values of invalid) {
    assert.throws(() => parsePreferences(form(values)));
  }
});

test("freshness and cold start have distinct actionable messages", () => {
  assert.equal(new Set(Object.values(feedStates).map((s) => s.title)).size, 5);
  assert.match(feedStates.WAITING_FOR_BATCH.copy, /server/);
  assert.match(feedStates.STALE.copy, /36 hours/);
  assert.match(feedStates.NEEDS_PREFERENCES.copy, /roles and skills/);
});
