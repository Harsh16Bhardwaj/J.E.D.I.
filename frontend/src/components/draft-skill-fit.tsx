"use client";

import {
  AlertCircle,
  Check,
  CheckCircle2,
  RefreshCw,
  Save,
  XCircle,
} from "lucide-react";
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

type RoleExperience =
  | "meets_minimum"
  | "below_minimum"
  | "unknown"
  | "not_listed";

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
    roleExperience: RoleExperience;
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

const statusMeta = {
  evidenced: {
    label: "Found in resume",
    Icon: CheckCircle2,
    className: "border-success/30 bg-success-surface text-success",
  },
  needs_review: {
    label: "Check this",
    Icon: AlertCircle,
    className: "border-warning/30 bg-warning-surface text-warning",
  },
  not_evidenced: {
    label: "Not found",
    Icon: XCircle,
    className: "border-destructive/30 bg-error-surface text-destructive",
  },
} as const;

function scoreLabel(score: number | null) {
  if (score === null) return "More information needed";
  if (score >= 80) return "Strong documented fit";
  if (score >= 60) return "Good documented fit";
  if (score >= 40) return "Partial documented fit";
  return "Low documented fit";
}

function experienceLabel(value: RoleExperience) {
  if (value === "meets_minimum") return "Meets listed experience";
  if (value === "below_minimum") return "Below listed experience";
  if (value === "unknown") return "Experience needs review";
  return "No minimum listed";
}

export function DraftSkillFit({
  draftId,
  revision,
}: {
  draftId: string;
  revision: number;
}) {
  const [viewingSaved, setViewingSaved] = useState(false);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();
  const [busy, setBusy] = useState<"compare" | "save" | "delete">();
  const path = `/api/job-drafts/${draftId}/skill-fit`;
  const savedPath = `${path}/saved`;
  const comparison = useSWR<FitReport>(
    `${path}?revision=${revision}`,
    (url: string) =>
      apiRequest<FitReport>(url, { signal: AbortSignal.timeout(15_000) }),
    { revalidateOnFocus: false },
  );
  const saved = useSWR<FitSnapshot | null>(savedPath, (url: string) =>
    apiRequest<FitSnapshot | null>(url, {
      signal: AbortSignal.timeout(15_000),
    }),
  );
  const report = viewingSaved ? saved.data?.report : comparison.data;

  async function compare() {
    if (busy) return;
    setBusy("compare");
    setError(undefined);
    setMessage(undefined);
    try {
      const updated = await apiRequest<FitReport>(
        `${path}?revision=${revision}`,
        { signal: AbortSignal.timeout(15_000) },
      );
      await comparison.mutate(updated, { revalidate: false });
      setViewingSaved(false);
      setMessage("Fit score updated from your saved resume.");
    } catch (refreshError) {
      setError(errorSummary(refreshError));
    } finally {
      setBusy(undefined);
    }
  }

  async function saveSnapshot() {
    if (busy || !comparison.data?.inputVersion) return;
    if (
      saved.data &&
      !window.confirm("Replace the saved comparison with these results?")
    )
      return;
    setBusy("save");
    setError(undefined);
    setMessage(undefined);
    try {
      await saved.mutate(
        await apiRequest<FitSnapshot>(savedPath, {
          method: "PUT",
          body: JSON.stringify({
            draftRevision: revision,
            inputVersion: comparison.data.inputVersion,
            expectedSavedVersion: saved.data?.report.inputVersion ?? null,
          }),
          signal: AbortSignal.timeout(15_000),
        }),
        { revalidate: false },
      );
      setMessage("Fit result saved with this private job brief.");
    } catch (saveError) {
      setError(errorSummary(saveError));
      void saved.mutate();
    } finally {
      setBusy(undefined);
    }
  }

  async function deleteSnapshot() {
    const version = saved.data?.report.inputVersion;
    if (busy || !version || !window.confirm("Delete this saved fit result?"))
      return;
    setBusy("delete");
    setError(undefined);
    setMessage(undefined);
    try {
      await apiRequest(`${savedPath}?inputVersion=${version}`, {
        method: "DELETE",
        signal: AbortSignal.timeout(15_000),
      });
      await saved.mutate(null, { revalidate: false });
      setViewingSaved(false);
      setMessage("Saved fit result deleted.");
    } catch (deleteError) {
      setError(errorSummary(deleteError));
      void saved.mutate();
    } finally {
      setBusy(undefined);
    }
  }

  const findings = report?.findings ?? [];
  const required = findings.filter(
    (finding) => finding.requirement.level === "required",
  );
  const evidenced = required.filter(
    (finding) => finding.status === "evidenced",
  ).length;
  const needsReview = required.filter(
    (finding) => finding.status === "needs_review",
  ).length;
  const missing = required.filter(
    (finding) => finding.status === "not_evidenced",
  ).length;
  const score = report?.assessment?.score ?? null;
  const isLoading = comparison.isLoading && !viewingSaved;
  const comparisonError = comparison.error
    ? errorSummary(comparison.error)
    : undefined;

  return (
    <section
      aria-labelledby="draft-skill-fit"
      className="mt-5 overflow-hidden rounded-xl border border-border bg-card"
    >
      <div className="border-b border-border bg-surface-subtle px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="desk-eyebrow">Private resume comparison</p>
            <h3 id="draft-skill-fit" className="mt-1 text-xl font-semibold">
              Resume fit
            </h3>
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              Your saved resume is checked automatically against this job.
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void compare()}
            disabled={Boolean(busy || isLoading)}
          >
            <RefreshCw
              className={`size-3.5 ${busy === "compare" ? "animate-spin" : ""}`}
            />
            {busy === "compare" ? "Recalculating…" : "Recalculate"}
          </Button>
        </div>
        <ol className="mt-4 grid gap-2 text-xs sm:grid-cols-3">
          {["Job details saved", "Resume checked", "Fit score ready"].map(
            (label, index) => (
              <li
                key={label}
                className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-muted-foreground"
              >
                <span className="grid size-5 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground">
                  {isLoading && index > 0 ? index + 1 : <Check className="size-3" />}
                </span>
                {label}
              </li>
            ),
          )}
        </ol>
      </div>

      <div className="space-y-5 p-5 sm:p-6">
        {(error || comparisonError) && (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-error-surface p-3 text-sm text-destructive"
          >
            {error ?? comparisonError}
          </div>
        )}
        {message && (
          <p
            role="status"
            className="rounded-lg border border-success/30 bg-success-surface p-3 text-sm text-success"
          >
            {message}
          </p>
        )}

        {isLoading && (
          <div role="status" className="grid gap-4 md:grid-cols-[12rem_1fr]">
            <div className="min-h-44 animate-pulse rounded-xl bg-muted" />
            <div className="space-y-3 py-2">
              <div className="h-6 w-52 animate-pulse rounded bg-muted" />
              <div className="h-4 w-full max-w-lg animate-pulse rounded bg-muted" />
              <div className="h-20 w-full animate-pulse rounded bg-muted" />
            </div>
          </div>
        )}

        {report && !report.hasResume && (
          <div className="rounded-xl border border-warning/30 bg-warning-surface p-5">
            <h4 className="font-semibold text-warning">Add your resume first</h4>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload or paste your resume once. JEDI will then show a fit score
              automatically for every saved job brief.
            </p>
            <Link
              href="/onboarding"
              className={buttonVariants({ className: "mt-4", size: "sm" })}
            >
              Add resume
            </Link>
          </div>
        )}

        {report?.hasResume && report.assessment && (
          <>
            <div className="grid gap-5 md:grid-cols-[13rem_1fr]">
              <div className="flex min-h-48 flex-col justify-between rounded-xl border border-primary/35 bg-surface-tint p-5">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">
                    Fit score
                  </p>
                  <p className="mt-3 font-mono text-5xl font-bold tracking-tight text-foreground">
                    {score === null ? "—" : score}
                    {score !== null && (
                      <span className="text-lg text-muted-foreground">/100</span>
                    )}
                  </p>
                </div>
                <div>
                  <p className="font-semibold">{scoreLabel(score)}</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    Resume evidence, not interview probability.
                  </p>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <h4 className="text-lg font-semibold">What the score means</h4>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    {report.assessment.basis}
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-lg border border-success/30 bg-success-surface p-3">
                    <strong className="block text-xl text-success">{evidenced}</strong>
                    <span className="text-xs text-muted-foreground">Required found</span>
                  </div>
                  <div className="rounded-lg border border-warning/30 bg-warning-surface p-3">
                    <strong className="block text-xl text-warning">{needsReview}</strong>
                    <span className="text-xs text-muted-foreground">Check</span>
                  </div>
                  <div className="rounded-lg border border-destructive/30 bg-error-surface p-3">
                    <strong className="block text-xl text-destructive">{missing}</strong>
                    <span className="text-xs text-muted-foreground">Not found</span>
                  </div>
                </div>
                <div className="rounded-lg border border-border p-3 text-sm">
                  <p className="font-medium">
                    {experienceLabel(report.assessment.roleExperience)}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {report.jobMinimumYears === null
                      ? "The posting does not state a minimum."
                      : `Job asks for ${report.jobMinimumYears}+ years · resume shows ${report.resumeYears === null ? "no reviewed total" : `${report.resumeYears} years`}.`}
                  </p>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 border-y border-border py-4">
              {!viewingSaved &&
                comparison.data?.inputVersion &&
                saved.data?.report.inputVersion !== comparison.data.inputVersion && (
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void saveSnapshot()}
                    disabled={Boolean(busy || saved.isLoading || saved.error)}
                  >
                    <Save className="size-3.5" />
                    {busy === "save"
                      ? "Saving…"
                      : saved.data
                        ? "Replace saved result"
                        : "Save this result"}
                  </Button>
                )}
              {saved.data && !viewingSaved && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={Boolean(busy)}
                  onClick={() => setViewingSaved(true)}
                >
                  View saved result
                </Button>
              )}
              {viewingSaved && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setViewingSaved(false)}
                >
                  Back to current score
                </Button>
              )}
              <span className="text-xs text-muted-foreground">
                Fit results are private to your account.
              </span>
            </div>

            {viewingSaved && saved.data && (
              <div className="rounded-lg border border-border bg-surface-subtle p-4 text-sm">
                <p className="font-semibold">
                  Saved result for {saved.data.title || "this job"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Resume reviewed {new Date(saved.data.resumeReviewedAt).toLocaleString()} · Saved {new Date(saved.data.savedAt).toLocaleString()}
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="mt-3"
                  disabled={Boolean(busy)}
                  onClick={() => void deleteSnapshot()}
                >
                  {busy === "delete" ? "Deleting…" : "Delete saved result"}
                </Button>
              </div>
            )}

            <div>
              <div className="flex flex-wrap items-end justify-between gap-2">
                <div>
                  <h4 className="text-lg font-semibold">Requirement breakdown</h4>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Open any item to see the exact resume evidence and what to improve.
                  </p>
                </div>
                <span className="text-xs text-muted-foreground">
                  {required.length
                    ? `${evidenced} of ${required.length} required items found`
                    : "No required skills identified"}
                </span>
              </div>
              <div className="mt-4 space-y-2">
                {findings.map(({ requirement, status, evidence, note }, index) => {
                  const meta = statusMeta[status];
                  const Icon = meta.Icon;
                  return (
                    <details
                      key={`${requirement.skills.join(":")}:${index}`}
                      className="group rounded-lg border border-border bg-surface-subtle open:bg-card"
                    >
                      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4 [&::-webkit-details-marker]:hidden">
                        <div className="min-w-0">
                          <p className="font-medium">
                            {requirement.skills.join(
                              requirement.match === "any" ? " or " : ", ",
                            ) || "Experience requirement"}
                          </p>
                          <p className="mt-1 text-xs capitalize text-muted-foreground">
                            {requirement.level === "uncertain"
                              ? "Requirement level unclear"
                              : requirement.level}
                            {requirement.experienceMinYears !== null &&
                              ` · ${requirement.experienceMinYears}+ years`}
                          </p>
                        </div>
                        <span
                          className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${meta.className}`}
                        >
                          <Icon className="size-3.5" />
                          {meta.label}
                        </span>
                      </summary>
                      <div className="border-t border-border px-4 py-3 text-sm">
                        <p className="leading-6 text-muted-foreground">
                          {requirement.text}
                        </p>
                        {evidence.length > 0 && (
                          <div className="mt-3 space-y-2">
                            <p className="text-xs font-semibold uppercase tracking-wide text-success">
                              Resume evidence
                            </p>
                            {evidence.map((quote, quoteIndex) => (
                              <p
                                key={quoteIndex}
                                className="border-l-2 border-success pl-3 text-xs leading-5"
                              >
                                {quote}
                              </p>
                            ))}
                          </div>
                        )}
                        {note && (
                          <p className="mt-3 text-xs leading-5 text-muted-foreground">
                            Next step: {note}
                          </p>
                        )}
                      </div>
                    </details>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
