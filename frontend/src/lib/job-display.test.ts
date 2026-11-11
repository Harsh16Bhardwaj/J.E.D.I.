import assert from "node:assert/strict";
import test from "node:test";

import { descriptionPreview, formatCompensationLpa, postedDaysAgo } from "./job-display";

test("card previews remove Markdown formatting while preserving skill names", () => {
  assert.equal(descriptionPreview("**Role:** Full Stack Developer\n**Location:** Delhi\n- React.js, C++, C#, .NET and `TypeScript`"),
    "Role: Full Stack Developer Location: Delhi React.js, C++, C#, .NET and TypeScript");
  assert.equal(descriptionPreview("## Responsibilities\nBuild [APIs](https://example.com) with __Python__."), "Responsibilities Build APIs with Python.");
  assert.equal(descriptionPreview(""), "");
});

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
