export type Preferences = {
  preferredTitles: string[];
  preferredLocations: string[];
  preferredSkills: string[];
  experienceMinYears: number | null;
  experienceMaxYears: number | null;
  salaryMin: number | null;
  salaryMax: number | null;
  salaryCurrency: string | null;
};

export type PersonalFeed = {
  status:
    | "NEEDS_PREFERENCES"
    | "WAITING_FOR_BATCH"
    | "READY"
    | "EMPTY"
    | "STALE";
  generatedAt: string | null;
  cohorts: string[];
  catalogCount: number;
  candidateCount: number;
  truncated: boolean;
  fallback?: boolean;
  latestAttempt: {
    status: string;
    at: string;
    errorCode: string | null;
  } | null;
  jobs: {
    id: string;
    roleTitle: string;
    companyName: string;
    location: string | null;
    workMode: string | null;
    score: number | null;
    reasons: string[];
    unknowns: string[];
  }[];
};

export const feedStates = {
  NEEDS_PREFERENCES: {
    title: "Make this space yours.",
    copy: "Choose the roles and skills you want to work with. Your feed will use your preferences.",
  },
  WAITING_FOR_BATCH: {
    title: "Your preferences are ready.",
    copy: "The server has not published its first daily job pool yet. You can compare a job with your resume while you wait.",
  },
  EMPTY: {
    title: "A quiet day in your orbit.",
    copy: "No current listings are available in your pool. Try broader preferences or bring a job description to compare.",
  },
  STALE: {
    title: "Showing the last completed brief.",
    copy: "This pool is more than 36 hours old. A new daily batch has not completed. Expired listings are still removed.",
  },
  READY: {
    title: "Your next move starts here.",
    copy: "A shared search of the market, ordered around your own preferences.",
  },
} satisfies Record<PersonalFeed["status"], { title: string; copy: string }>;

export function parsePreferences(form: FormData): Preferences {
  const tags = (key: string) => [
    ...new Set(
      String(form.get(key) ?? "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
  const number = (key: string) => {
    const raw = String(form.get(key) ?? "").trim();
    if (!raw) return null;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0)
      throw new Error("Enter positive numbers or leave optional fields empty.");
    return value;
  };
  const result = {
    preferredTitles: tags("titles"),
    preferredLocations: tags("locations"),
    preferredSkills: tags("skills"),
    experienceMinYears: number("experienceMin"),
    experienceMaxYears: number("experienceMax"),
    salaryMin: number("salaryMin"),
    salaryMax: number("salaryMax"),
    salaryCurrency: String(form.get("currency") || "INR")
      .trim()
      .toUpperCase(),
  };
  if (!result.preferredTitles.length && !result.preferredSkills.length)
    throw new Error("Add at least one target role or skill.");
  for (const [min, max] of [
    [result.experienceMinYears, result.experienceMaxYears],
    [result.salaryMin, result.salaryMax],
  ]) {
    if (min !== null && max !== null && min > max)
      throw new Error("Minimum values must be no greater than maximum values.");
  }
  if (
    (result.experienceMinYears ?? 0) > 80 ||
    (result.experienceMaxYears ?? 0) > 80
  )
    throw new Error("Experience must be between 0 and 80 years.");
  return result;
}
