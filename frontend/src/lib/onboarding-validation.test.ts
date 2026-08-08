import assert from "node:assert/strict";
import test from "node:test";

import {
  type OnboardingFormState,
  validateOnboardingForm,
} from "./onboarding-validation";

const validForm: OnboardingFormState = {
  preferredTitles: ["Backend Engineer"],
  preferredLocations: ["Remote"],
  preferredSkills: ["Python", "FastAPI"],
  experienceRange: "2-3",
  salaryMinLpa: "8",
};

test("requires every onboarding section before submission", () => {
  const result = validateOnboardingForm({
    preferredTitles: [],
    preferredLocations: [],
    preferredSkills: [],
    experienceRange: "",
    salaryMinLpa: "",
  });

  assert.equal(result.values, undefined);
  assert.deepEqual(Object.keys(result.errors).sort(), [
    "experienceRange",
    "preferredLocations",
    "preferredSkills",
    "preferredTitles",
    "salaryMinLpa",
  ]);
});

test("rejects malformed tags, experience choices, and salary", () => {
  const result = validateOnboardingForm({
    ...validForm,
    preferredSkills: ["---"],
    experienceRange: "1-2",
    salaryMinLpa: "not-a-number",
  });

  assert.equal(result.values, undefined);
  assert.match(result.errors.preferredSkills ?? "", /letter or number/i);
  assert.match(result.errors.experienceRange ?? "", /select/i);
  assert.match(result.errors.salaryMinLpa ?? "", /valid non-negative number/i);
});

test("converts a valid LPA preference to annual INR", () => {
  const result = validateOnboardingForm({
    ...validForm,
    preferredTitles: ["  Backend Engineer  "],
  });

  assert(result.values);
  assert.deepEqual(result.errors, {});
  assert.deepEqual(result.values.preferredTitles, ["Backend Engineer"]);
  assert.equal(result.values.experienceMinYears, 2);
  assert.equal(result.values.experienceMaxYears, 3);
  assert.equal(result.values.salaryMin, 800_000);
  assert.equal(result.values.salaryMax, null);
  assert.equal(result.values.salaryCurrency, "INR");
});

test("maps 8+ years to an open-ended range", () => {
  const result = validateOnboardingForm({
    ...validForm,
    experienceRange: "8+",
  });

  assert(result.values);
  assert.equal(result.values.experienceMinYears, 8);
  assert.equal(result.values.experienceMaxYears, null);
});
