export type JobSearchCriteria = {
  postedDays: number;
  salaryMinimum: string;
  preferredRoles: string;
  experienceYears: string;
  companyType: "STARTUP" | "MNC" | "PRODUCT_GIANTS" | "ALL";
  locations: string;
};

const sourceList = [
  "Official company career pages",
  "LinkedIn Jobs",
  "Naukri",
  "Indeed",
  "Wellfound",
  "Instahyre",
  "Cutshort",
  "Foundit",
  "Glassdoor",
  "Google Jobs",
  "Hirist",
  "iimjobs",
  "Dice",
  "Built In",
  "Y Combinator Work at a Startup",
  "Remote OK",
  "We Work Remotely",
  "Levels.fyi Jobs",
  "Greenhouse-hosted company boards",
  "Lever-hosted company boards",
];

const companyTypeLabels: Record<JobSearchCriteria["companyType"], string> = {
  STARTUP: "startup",
  MNC: "multinational company (MNC)",
  PRODUCT_GIANTS: "large product company",
  ALL: "all company types",
};

function commaList(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function isJobSearchComplete(criteria: JobSearchCriteria): boolean {
  return (
    criteria.postedDays >= 1 &&
    criteria.salaryMinimum.trim() !== "" &&
    Number(criteria.salaryMinimum) >= 0 &&
    commaList(criteria.preferredRoles).length > 0 &&
    criteria.experienceYears.trim() !== "" &&
    Number(criteria.experienceYears) >= 0 &&
    commaList(criteria.locations).length > 0
  );
}

export function buildJobSearchPrompt(criteria: JobSearchCriteria): string {
  const roles = commaList(criteria.preferredRoles);
  const locations = commaList(criteria.locations);
  const experience = Math.max(0, Number(criteria.experienceYears) || 0);
  const experienceMin = Math.max(0, experience - 1);
  const experienceMax = experience + 1;
  const salary = Math.max(0, Number(criteria.salaryMinimum) || 0);
  const postedDays = Math.min(30, Math.max(1, Number(criteria.postedDays) || 1));

  return `Use internet search to find currently open jobs for the requirements below.

SEARCH REQUIREMENTS
- Posted within the last ${postedDays} day(s). JEDI never accepts jobs older than 30 days.
- Minimum annual salary: INR ${salary}.
- Preferred roles: ${JSON.stringify(roles)}.
- Candidate experience: ${experience} year(s). Include suitable roles asking for ${experienceMin}-${experienceMax} years when the rest of the role is a strong match.
- Company type: ${companyTypeLabels[criteria.companyType]}.
- Preferred locations: ${JSON.stringify(locations)}. Include remote roles that explicitly accept candidates from India when relevant.

SEARCH SOURCES
Search across these 20 source categories and prioritize the employer's own careers page when it is available:
${sourceList.map((source, index) => `${index + 1}. ${source}`).join("\n")}

QUALITY RULES
1. Use web search. Do not answer from memory.
2. Include only jobs that appear open and have a working application URL.
3. Prefer a direct employer application URL over an aggregator URL.
4. Remove duplicates using company, role, location, and application URL.
5. Do not invent salary, dates, experience, skills, work mode, or deadlines. Use null when a value is not stated.
6. Keep reasonable flexibility around titles, locations, and experience. Reject clearly unrelated roles.
7. Return no more than 50 high-quality jobs.
8. Verify postedAt from the source. Omit a job when its posting date is unavailable or older than the requested window; JEDI rejects missing dates and jobs older than 30 days.

OUTPUT CONTRACT
Create and attach a file named jedi-jobs-YYYY-MM-DD.json. The file must contain exactly one valid JSON object. Do not include Markdown, code fences, comments, citations, explanations, or text outside the JSON object.

Use this exact shape and field names:
{
  "externalBatchId": "llm-search-YYYY-MM-DD-UNIQUE_ID",
  "schemaVersion": "1.0",
  "promptVersion": "jedi-tutorial-v1",
  "generatedAt": "ISO-8601 UTC timestamp",
  "jobs": [
    {
      "companyName": "Example Company",
      "roleTitle": "Example Role",
      "description": "A non-empty job description",
      "applyUrl": "https://company.example/jobs/role",
      "roleFamily": null,
      "seniority": null,
      "location": null,
      "workMode": null,
      "employmentType": null,
      "skills": [],
      "experienceMinYears": null,
      "experienceMaxYears": null,
      "salaryMin": null,
      "salaryMax": null,
      "salaryCurrency": null,
      "postedAt": "ISO-8601 verified posting timestamp",
      "applicationDeadline": null,
      "canApplyNow": null
    }
  ]
}

Replace every placeholder with a real value. Ensure externalBatchId is unique. If your interface cannot attach a file, return only the raw JSON object so it can be copied directly.`;
}
