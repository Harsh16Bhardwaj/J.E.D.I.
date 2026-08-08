export type OnboardingFormState = {
  preferredTitles: string[];
  preferredLocations: string[];
  preferredSkills: string[];
  experienceRange: string;
  salaryMinLpa: string;
};

export type OnboardingFieldErrors = Partial<
  Record<keyof OnboardingFormState, string>
>;

export type OnboardingSubmission = Pick<
  OnboardingFormState,
  "preferredTitles" | "preferredLocations" | "preferredSkills"
> & {
  experienceMinYears: number;
  experienceMaxYears: number | null;
  salaryMin: number;
  salaryMax: null;
  salaryCurrency: "INR";
};

export const experienceRanges = {
  "0-1": { label: "0–1 years", minimum: 0, maximum: 1 },
  "2-3": { label: "2–3 years", minimum: 2, maximum: 3 },
  "3-5": { label: "3–5 years", minimum: 3, maximum: 5 },
  "5-7": { label: "5–7 years", minimum: 5, maximum: 7 },
  "8+": { label: "8+ years", minimum: 8, maximum: null },
} as const;

type ValidationResult =
  | { errors: OnboardingFieldErrors; values?: never }
  | { errors: OnboardingFieldErrors; values: OnboardingSubmission };

const tagLimits = {
  preferredTitles: { label: "target title", maximum: 100 },
  preferredLocations: { label: "preferred location", maximum: 100 },
  preferredSkills: { label: "skill", maximum: 200 },
} as const;

function validateTags(
  key: keyof typeof tagLimits,
  values: string[],
  errors: OnboardingFieldErrors,
) {
  const { label, maximum } = tagLimits[key];
  if (!values.length) {
    errors[key] = `Add at least one ${label}.`;
    return;
  }
  if (values.length > maximum) {
    errors[key] = `Add no more than ${maximum} ${label} entries.`;
    return;
  }
  if (values.some((value) => !value.trim())) {
    errors[key] = `Remove empty ${label} entries.`;
    return;
  }
  if (values.some((value) => !/[\p{L}\p{N}]/u.test(value))) {
    errors[key] = `Each ${label} must contain a letter or number.`;
    return;
  }
  if (values.some((value) => value.trim().length > 100)) {
    errors[key] = `Keep each ${label} under 100 characters.`;
  }
}

function requiredNumber(
  value: string,
  label: string,
  key: keyof OnboardingFormState,
  errors: OnboardingFieldErrors,
  maximum?: number,
): number | undefined {
  if (!value.trim()) {
    errors[key] = `Enter ${label}.`;
    return undefined;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    errors[key] = `${label} must be a valid non-negative number.`;
    return undefined;
  }
  if (maximum !== undefined && parsed > maximum) {
    errors[key] = `${label} cannot exceed ${maximum}.`;
    return undefined;
  }
  return parsed;
}

export function validateOnboardingForm(
  form: OnboardingFormState,
): ValidationResult {
  const errors: OnboardingFieldErrors = {};
  validateTags("preferredTitles", form.preferredTitles, errors);
  validateTags("preferredLocations", form.preferredLocations, errors);
  validateTags("preferredSkills", form.preferredSkills, errors);

  const experience = experienceRanges[
    form.experienceRange as keyof typeof experienceRanges
  ];
  if (!experience) {
    errors.experienceRange = "Select your experience range.";
  }
  const salaryMinLpa = requiredNumber(
    form.salaryMinLpa,
    "minimum salary in LPA",
    "salaryMinLpa",
    errors,
    10_000,
  );

  if (Object.keys(errors).length) return { errors };

  return {
    errors,
    values: {
      preferredTitles: form.preferredTitles.map((value) => value.trim()),
      preferredLocations: form.preferredLocations.map((value) => value.trim()),
      preferredSkills: form.preferredSkills.map((value) => value.trim()),
      experienceMinYears: experience!.minimum,
      experienceMaxYears: experience!.maximum,
      salaryMin: salaryMinLpa! * 100_000,
      salaryMax: null,
      salaryCurrency: "INR",
    },
  };
}
