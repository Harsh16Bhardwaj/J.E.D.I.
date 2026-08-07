export type OnboardingFormState = {
  resumeText: string;
  preferredTitles: string[];
  preferredLocations: string[];
  preferredSkills: string[];
  experienceMinYears: string;
  experienceMaxYears: string;
  salaryMin: string;
  salaryMax: string;
  salaryCurrency: string;
};

export type OnboardingFieldErrors = Partial<
  Record<keyof OnboardingFormState, string>
>;

export type OnboardingSubmission = Omit<
  OnboardingFormState,
  | "experienceMinYears"
  | "experienceMaxYears"
  | "salaryMin"
  | "salaryMax"
> & {
  experienceMinYears: number;
  experienceMaxYears: number;
  salaryMin: number;
  salaryMax: number;
};

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
  const resumeText = form.resumeText.trim();
  if (!resumeText) {
    errors.resumeText = "Add your profile or resume content.";
  } else if (resumeText.length > 100_000) {
    errors.resumeText = "Profile or resume content cannot exceed 100,000 characters.";
  }

  validateTags("preferredTitles", form.preferredTitles, errors);
  validateTags("preferredLocations", form.preferredLocations, errors);
  validateTags("preferredSkills", form.preferredSkills, errors);

  const experienceMinYears = requiredNumber(
    form.experienceMinYears,
    "minimum experience",
    "experienceMinYears",
    errors,
    80,
  );
  const experienceMaxYears = requiredNumber(
    form.experienceMaxYears,
    "maximum experience",
    "experienceMaxYears",
    errors,
    80,
  );
  const salaryMin = requiredNumber(
    form.salaryMin,
    "minimum salary",
    "salaryMin",
    errors,
    999_999_999_999,
  );
  const salaryMax = requiredNumber(
    form.salaryMax,
    "maximum salary",
    "salaryMax",
    errors,
    999_999_999_999,
  );

  if (
    experienceMinYears !== undefined &&
    experienceMaxYears !== undefined &&
    experienceMinYears > experienceMaxYears
  ) {
    errors.experienceMaxYears =
      "Maximum experience must be greater than or equal to the minimum.";
  }
  if (
    salaryMin !== undefined &&
    salaryMax !== undefined &&
    salaryMin > salaryMax
  ) {
    errors.salaryMax =
      "Maximum salary must be greater than or equal to the minimum.";
  }

  const salaryCurrency = form.salaryCurrency.trim().toUpperCase();
  if (!salaryCurrency) {
    errors.salaryCurrency = "Enter a salary currency.";
  } else if (!/^[A-Z]{3}$/.test(salaryCurrency)) {
    errors.salaryCurrency = "Use a three-letter currency code such as INR or USD.";
  }

  if (Object.keys(errors).length) return { errors };

  return {
    errors,
    values: {
      ...form,
      resumeText,
      preferredTitles: form.preferredTitles.map((value) => value.trim()),
      preferredLocations: form.preferredLocations.map((value) => value.trim()),
      preferredSkills: form.preferredSkills.map((value) => value.trim()),
      experienceMinYears: experienceMinYears!,
      experienceMaxYears: experienceMaxYears!,
      salaryMin: salaryMin!,
      salaryMax: salaryMax!,
      salaryCurrency,
    },
  };
}
