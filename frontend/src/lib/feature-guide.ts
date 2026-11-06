export const featureGuide = [
  {
    id: "job-intake",
    route: "/jobs/intake",
    title: "Bring a job",
    audience: "member",
    prerequisite: "A posting link or job description",
    steps: [
      "Preview a Greenhouse, Lever, or Ashby posting, or paste the description.",
      "Review the extracted requirements and save a private draft.",
    ],
    sample: "Backend Engineer\nRequirements:\n3+ years of Python or Java.\nAWS is a plus.",
  },
  {
    id: "resume-comparison",
    route: "/jobs/intake",
    title: "Compare resume evidence",
    audience: "member",
    prerequisite: "A saved draft and reviewed resume evidence",
    steps: [
      "Open the draft and choose Compare with saved resume.",
      "Check each requirement and confirm years using a specific skill when the report asks.",
    ],
  },
  {
    id: "application-moves",
    route: "/applications",
    title: "Move an application",
    audience: "member",
    prerequisite: "An application started from a shared job",
    steps: [
      "Open an application card and record the stage you have confirmed.",
      "For a backward move or reopening, record a correction and explain why.",
    ],
  },
  {
    id: "scraper-recovery",
    route: "/scraper",
    title: "Review and recover a scraper run",
    audience: "owner",
    prerequisite: "Group owner access and configured source boards",
    steps: [
      "Check Sources for recurring failures and Runs for retry timing.",
      "Use Stop & review to pause, then continue collection or import selected postings.",
      "If normalization is interrupted, reopen the run and resume the saved step.",
    ],
  },
  {
    id: "email-dispatch",
    route: "/settings/email",
    title: "Manage group dispatch",
    audience: "owner",
    prerequisite: "Group owner access and configured mail transport",
    steps: [
      "Review recipients and delivery outcomes in Email settings.",
      "Confirm manual sends and check the ledger for failed deliveries before retrying.",
    ],
  },
] as const;
