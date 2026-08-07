import assert from "node:assert/strict";
import test from "node:test";

import {
  type OnboardingFormState,
  validateOnboardingForm,
} from "./onboarding-validation";

const validForm: OnboardingFormState = {
  resumeText: "Python and FastAPI backend engineer",
  preferredTitles: ["Backend Engineer"],
  preferredLocations: ["Remote"],
  preferredSkills: ["Python", "FastAPI"],
  experienceMinYears: "0",
  experienceMaxYears: "2",
  salaryMin: "800000",
  salaryMax: "4000000",
  salaryCurrency: "inr",
};

test("requires every onboarding section before submission", () => {
  const result = validateOnboardingForm({
    resumeText: "",
    preferredTitles: [],
    preferredLocations: [],
    preferredSkills: [],
    experienceMinYears: "",
    experienceMaxYears: "",
    salaryMin: "",
    salaryMax: "",
    salaryCurrency: "",
  });

  assert.equal(result.values, undefined);
  assert.deepEqual(Object.keys(result.errors).sort(), [
    "experienceMaxYears",
    "experienceMinYears",
    "preferredLocations",
    "preferredSkills",
    "preferredTitles",
    "resumeText",
    "salaryCurrency",
    "salaryMax",
    "salaryMin",
  ]);
});

test("rejects malformed tags, ranges, and currency codes", () => {
  const result = validateOnboardingForm({
    ...validForm,
    preferredSkills: ["---"],
    experienceMinYears: "3",
    experienceMaxYears: "1",
    salaryMin: "not-a-number",
    salaryCurrency: "rupees",
  });

  assert.equal(result.values, undefined);
  assert.match(result.errors.preferredSkills ?? "", /letter or number/i);
  assert.match(result.errors.experienceMaxYears ?? "", /greater than or equal/i);
  assert.match(result.errors.salaryMin ?? "", /valid non-negative number/i);
  assert.match(result.errors.salaryCurrency ?? "", /three-letter currency/i);
});

test("returns normalized values for a complete valid form", () => {
  const result = validateOnboardingForm({
    ...validForm,
    resumeText: `  ${validForm.resumeText}  `,
    preferredTitles: ["  Backend Engineer  "],
  });

  assert(result.values);
  assert.deepEqual(result.errors, {});
  assert.equal(result.values.resumeText, validForm.resumeText);
  assert.deepEqual(result.values.preferredTitles, ["Backend Engineer"]);
  assert.equal(result.values.experienceMinYears, 0);
  assert.equal(result.values.salaryMax, 4_000_000);
  assert.equal(result.values.salaryCurrency, "INR");
});
