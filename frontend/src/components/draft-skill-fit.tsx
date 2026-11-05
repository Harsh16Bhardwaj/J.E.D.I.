"use client";

import Link from "next/link";
import { useState } from "react";
import { Button, buttonVariants } from "@/components/ui/button";
import { apiRequest, errorSummary } from "@/lib/api";

type FitFinding = {
  requirement: {
    level: "required" | "preferred" | "uncertain";
    match: "all" | "any";
    skills: string[];
    experienceMinYears: number | null;
    text: string;
  };
  status: "evidenced" | "needs_review" | "not_evidenced";
  evidence: string[];
  note: string | null;
};

type FitReport = {
  hasResume: boolean;
  findings: FitFinding[];
  jobMinimumYears: number | null;
  resumeYears: number | null;
};

const statusLabels = {
  evidenced: "Evidenced",
  needs_review: "Needs review",
  not_evidenced: "No resume evidence",
};

export function DraftSkillFit({ draftId, revision }: { draftId: string; revision: number }) {
  const [report, setReport] = useState<FitReport>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  async function compare() {
    setLoading(true);
    setError(undefined);
    try {
      setReport(await apiRequest<FitReport>(`/api/job-drafts/${draftId}/skill-fit?revision=${revision}`, {
        signal: AbortSignal.timeout(15_000),
      }));
    } catch (error) {
      setError(errorSummary(error));
    } finally {
      setLoading(false);
    }
  }

  const required = report?.findings.filter((finding) => finding.requirement.level === "required") ?? [];
  const evidenced = required.filter((finding) => finding.status === "evidenced").length;

  return (
    <section aria-labelledby="draft-skill-fit" className="space-y-3 border-t border-border pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="draft-skill-fit" className="font-bold">Resume evidence</h3>
        <Button type="button" size="sm" variant="outline" onClick={() => void compare()} disabled={loading}>
          {loading ? "Comparing…" : report ? "Compare again" : "Compare with saved resume"}
        </Button>
      </div>
      {error && <p role="alert" className="text-sm text-coral">{error}</p>}
      {report && !report.hasResume && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Save your resume evidence first to compare it with this draft.</p>
          <Link href="/onboarding" className={buttonVariants({ size: "sm", variant: "outline" })}>Add resume evidence</Link>
        </div>
      )}
      {report?.hasResume && (
        <>
          <p role="status" className="text-sm text-muted-foreground">
            {required.length ? `${evidenced} of ${required.length} required skill items clearly evidenced.` : "Add required skills to the draft to see required skill coverage."}
          </p>
          {report.jobMinimumYears !== null && (
            <p className="text-sm text-muted-foreground">
              Listed minimum {report.jobMinimumYears} years · resume total {report.resumeYears === null ? "unavailable" : `${report.resumeYears} years`}
            </p>
          )}
          <ul className="max-h-96 space-y-2 overflow-auto">
            {report.findings.map(({ requirement, status, evidence, note }, index) => (
              <li key={index} className="rounded-lg border border-border p-3 text-sm">
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="font-bold">{requirement.skills.join(requirement.match === "any" ? " or " : ", ")}</p>
                  <p className="text-xs font-bold">{statusLabels[status]}</p>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {requirement.level === "uncertain" ? "Requirement level unclear" : requirement.level}
                  {requirement.experienceMinYears !== null && ` · minimum ${requirement.experienceMinYears} years`}
                </p>
                <p className="mt-1 break-words text-muted-foreground">{requirement.text}</p>
                {evidence.map((quote, quoteIndex) => (
                  <p key={quoteIndex} className="mt-1 break-words border-l border-purple pl-2 text-xs">{quote}</p>
                ))}
                {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
