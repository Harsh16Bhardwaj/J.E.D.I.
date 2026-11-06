"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { Button, buttonVariants } from "@/components/ui/button";
import { apiRequest, errorSummary } from "@/lib/api";

type FitFinding = {
  requirement: {
    level: "required" | "preferred" | "uncertain";
    match: "all" | "any" | "review";
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
  inputVersion: string | null;
  findings: FitFinding[];
  jobMinimumYears: number | null;
  resumeYears: number | null;
  assessment?: {
    version: string;
    score: number | null;
    basis: string;
    roleExperience: "meets_minimum" | "below_minimum" | "unknown" | "not_listed";
  } | null;
};

type FitSnapshot = {
  draftRevision: number;
  resumeReviewedAt: string;
  savedAt: string;
  title: string;
  employer: string;
  report: FitReport;
};

const statusLabels = {
  evidenced: "Evidenced",
  needs_review: "Needs review",
  not_evidenced: "No resume evidence",
};

export function DraftSkillFit({ draftId, revision }: { draftId: string; revision: number }) {
  const [current, setCurrent] = useState<FitReport>();
  const [viewingSaved, setViewingSaved] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();
  const [busy, setBusy] = useState<"compare" | "save" | "delete">();
  const path = `/api/job-drafts/${draftId}/skill-fit`;
  const savedPath = `${path}/saved`;
  const saved = useSWR<FitSnapshot | null>(
    savedPath, (url: string) => apiRequest<FitSnapshot | null>(url, { signal: AbortSignal.timeout(15_000) }),
  );
  const report = viewingSaved ? saved.data?.report : current;

  async function compare() {
    if (busy) return;
    setBusy("compare");
    setError(undefined);
    setMessage(undefined);
    try {
      setCurrent(await apiRequest<FitReport>(`${path}?revision=${revision}`, {
        signal: AbortSignal.timeout(15_000),
      }));
      setViewingSaved(false);
    } catch (error) {
      setError(errorSummary(error));
    } finally {
      setBusy(undefined);
    }
  }

  async function saveSnapshot() {
    if (busy || !current?.inputVersion) return;
    if (saved.data && !window.confirm("Replace the saved comparison with these results?")) return;
    setBusy("save");
    setError(undefined);
    setMessage(undefined);
    try {
      await saved.mutate(await apiRequest<FitSnapshot>(savedPath, {
        method: "PUT",
        body: JSON.stringify({
          draftRevision: revision,
          inputVersion: current.inputVersion,
          expectedSavedVersion: saved.data?.report.inputVersion ?? null,
        }),
        signal: AbortSignal.timeout(15_000),
      }), { revalidate: false });
      setMessage("Comparison saved to this private draft.");
    } catch (error) {
      setError(errorSummary(error));
      void saved.mutate();
    } finally {
      setBusy(undefined);
    }
  }

  async function deleteSnapshot() {
    const version = saved.data?.report.inputVersion;
    if (busy || !version || !window.confirm("Delete this saved comparison?")) return;
    setBusy("delete");
    setError(undefined);
    setMessage(undefined);
    try {
      await apiRequest(`${savedPath}?inputVersion=${version}`, {
        method: "DELETE", signal: AbortSignal.timeout(15_000),
      });
      await saved.mutate(null, { revalidate: false });
      setViewingSaved(false);
      setMessage("Saved comparison deleted.");
    } catch (error) {
      setError(errorSummary(error));
      void saved.mutate();
    } finally {
      setBusy(undefined);
    }
  }

  const required = report?.findings.filter((finding) => finding.requirement.level === "required") ?? [];
  const evidenced = required.filter((finding) => finding.status === "evidenced").length;

  return (
    <section aria-labelledby="draft-skill-fit" className="space-y-3 border-t border-border pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="draft-skill-fit" className="font-bold">Resume evidence</h3>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => void compare()} disabled={Boolean(busy)}>
            {busy === "compare" ? "Comparing…" : report ? "Compare again" : "Compare with saved resume"}
          </Button>
          {saved.data && !viewingSaved && <Button type="button" size="sm" variant="outline" disabled={Boolean(busy)} onClick={() => setViewingSaved(true)}>View saved comparison</Button>}
        </div>
      </div>
      {error && <p role="alert" className="text-sm text-coral">{error}</p>}
      {message && <p role="status" className="text-sm text-acid">{message}</p>}
      {saved.isLoading && <p role="status" className="text-sm text-muted-foreground">Checking for a saved comparison…</p>}
      {saved.error && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-coral">{errorSummary(saved.error)}</p>
          <Button type="button" size="sm" variant="outline" onClick={() => void saved.mutate()}>Retry saved comparison</Button>
        </div>
      )}
      {viewingSaved && saved.data && (
        <div className="space-y-2 rounded-lg border border-border p-3 text-sm">
          <p className="font-bold">Saved comparison for {saved.data.title || "this job"}</p>
          <p className="text-muted-foreground">
            Draft revision {saved.data.draftRevision} · Resume reviewed {new Date(saved.data.resumeReviewedAt).toLocaleString()} · Saved {new Date(saved.data.savedAt).toLocaleString()}
          </p>
          {saved.data.report.assessment && <p className="text-xs text-muted-foreground">Scoring version {saved.data.report.assessment.version}</p>}
          <Button type="button" size="sm" variant="outline" disabled={Boolean(busy)} onClick={() => void deleteSnapshot()}>
            {busy === "delete" ? "Deleting…" : "Delete saved comparison"}
          </Button>
        </div>
      )}
      {report && !report.hasResume && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Save your resume evidence first to compare it with this draft.</p>
          <Link href="/onboarding" className={buttonVariants({ size: "sm", variant: "outline" })}>Add resume evidence</Link>
        </div>
      )}
      {report?.hasResume && (
        <>
          {!viewingSaved && current?.inputVersion && saved.data?.report.inputVersion !== current.inputVersion && (
            <div className="space-y-2">
              <Button type="button" size="sm" variant="outline" disabled={Boolean(busy || saved.isLoading || saved.error)} onClick={() => void saveSnapshot()}>
                {busy === "save" ? "Saving…" : saved.data ? "Replace saved comparison" : "Save comparison"}
              </Button>
              <p className="text-xs text-muted-foreground">A private saved comparison keeps the job and resume evidence used for the score.</p>
            </div>
          )}
          {report.assessment && (
            <div className="rounded-lg border border-purple/30 bg-purple/5 p-3">
              <p className="font-bold">
                {report.assessment.score === null
                  ? "Documented fit score unavailable"
                  : `Documented fit ${report.assessment.score}/100`}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">{report.assessment.basis}</p>
              {report.assessment.roleExperience === "below_minimum" && (
                <p className="mt-1 text-xs text-coral">Reviewed total experience is below the listed minimum.</p>
              )}
            </div>
          )}
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
