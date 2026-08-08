import assert from "node:assert/strict";
import test from "node:test";

import { formatCompensationLpa, postedDaysAgo } from "./job-display";

test("formats annual INR compensation in LPA", () => {
  assert.equal(
    formatCompensationLpa({
      salaryMin: 800_000,
      salaryMax: 1_200_000,
      salaryCurrency: "INR",
      salaryPeriod: "YEARLY",
    }),
    "8-12 LPA",
  );
});

test("annualizes monthly internship compensation while retaining its period", () => {
  assert.equal(
    formatCompensationLpa({
      salaryMin: 30_000,
      salaryMax: 50_000,
      salaryCurrency: "INR",
      salaryPeriod: "MONTHLY",
    }),
    "3.6-6 LPA · ₹30K-₹50K/month",
  );
});

test("uses the batch creation timestamp for posted age", () => {
  assert.equal(
    postedDaysAgo("2026-08-05T12:00:00Z", new Date("2026-08-08T12:00:00Z")),
    "Posted 3 days ago",
  );
  assert.equal(
    postedDaysAgo("2026-08-08T11:00:00Z", new Date("2026-08-08T12:00:00Z")),
    "Posted today",
  );
});
