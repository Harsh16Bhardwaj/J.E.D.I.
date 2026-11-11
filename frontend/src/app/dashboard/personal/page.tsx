"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { ArrowUpRight, FileSearch, RefreshCw, Settings2 } from "lucide-react";
import { apiRequest, errorSummary } from "@/lib/api";
import {
  feedStates,
  parsePreferences,
  type PersonalFeed,
  type Preferences,
} from "@/lib/personal-feed";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

export default function PersonalDashboard() {
  const feed = useSWR<PersonalFeed>("/api/recommendations", {
    shouldRetryOnError: false,
  });
  const preferences = useSWR<Preferences>("/api/preferences", {
    shouldRetryOnError: false,
  });
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string>();
  const state = feed.data ? feedStates[feed.data.status] : undefined;

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaveError(undefined);
    const form = new FormData(event.currentTarget);
    setSaving(true);
    try {
      const value = await apiRequest<Preferences>("/api/preferences", {
        method: "PUT",
        body: JSON.stringify(parsePreferences(form)),
      });
      await preferences.mutate(value, { revalidate: false });
      await feed.mutate();
      setEditing(false);
    } catch (error) {
      setSaveError(
        error instanceof Error ? error.message : errorSummary(error),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="personal-space space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Daily Feed
          </h1>
          {feed.data?.generatedAt && (
            <p className="mt-2 text-sm text-muted-foreground">
              Updated {new Date(feed.data.generatedAt).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            className="min-h-10"
            onClick={() => {
              setSaveError(undefined);
              setEditing(true);
            }}
          >
            <Settings2 className="size-4" /> Preferences
          </Button>
          <Link
            className="inline-flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm hover:bg-muted"
            href="/jobs/intake"
          >
            Compare a job <ArrowUpRight className="size-4" />
          </Link>
        </div>
      </header>
      {feed.error && (
        <div
          role="alert"
          className="rounded-xl border border-coral/30 bg-coral/5 p-5"
        >
          <p className="font-medium">Your feed could not load.</p>
          <p className="my-2 text-sm text-muted-foreground">
            {errorSummary(feed.error)}
          </p>
          <Button
            variant="outline"
            disabled={feed.isValidating}
            onClick={() => void feed.mutate()}
          >
            <RefreshCw className="size-4" />
            {feed.isValidating ? "Retrying…" : "Retry"}
          </Button>
        </div>
      )}
      {feed.isLoading && (
        <div role="status" className="grid gap-4 md:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-48 animate-pulse rounded-xl border border-border bg-card"
            />
          ))}
          <span className="sr-only">Loading recommendations</span>
        </div>
      )}
      {feed.data?.latestAttempt?.status === "FAILED" && (
        <p
          role="status"
          className="rounded-lg border border-coral/30 p-4 text-sm text-coral"
        >
          The latest refresh failed.
        </p>
      )}
      {feed.data?.status === "STALE" && (
        <p role="status" className="text-sm text-muted-foreground">
          {state?.copy}
        </p>
      )}
      {feed.data && (
        <section aria-labelledby="personal-jobs">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="personal-jobs" className="text-xl font-semibold">
                Shortlist
              </h2>
              {feed.data.jobs.length > 0 && (
                <p className="mt-1 text-xs text-muted-foreground">
                  Showing {feed.data.jobs.length} of {feed.data.candidateCount}
                </p>
              )}
            </div>
            <Button
              variant="ghost"
              disabled={feed.isValidating}
              onClick={() => void feed.mutate()}
            >
              <RefreshCw
                className={`size-4 ${feed.isValidating ? "animate-spin" : ""}`}
              />{" "}
              Refresh view
            </Button>
          </div>
          {feed.data.truncated && (
            <p className="mb-4 text-xs text-coral">
              This batch sampled the newest 5,000 listings. It does not cover
              the entire catalog.
            </p>
          )}
          {feed.data.fallback && (
            <p className="mb-4 text-xs text-muted-foreground">
              Your role pool is empty, so you are seeing the general discovery
              pool.
            </p>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            {feed.data.jobs.map((job) => (
              <article
                key={job.id}
                className="group rounded-xl border border-border bg-card p-4 transition-colors sm:p-5 hover:border-acid/40"
              >
                <div className="flex items-start justify-between gap-4">
                  <p className="font-mono text-xs text-muted-foreground">
                    {job.companyName}
                  </p>
                  <div className="text-right">
                    <strong className="text-2xl font-medium text-acid">
                      {job.score ?? "—"}
                    </strong>
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      Preference / 100
                    </p>
                  </div>
                </div>
                <h3 className="mt-2 text-xl font-semibold">
                  <Link href={`/jobs/${job.id}`} className="hover:text-acid">
                    {job.roleTitle}
                    <ArrowUpRight className="ml-2 inline size-4" />
                  </Link>
                </h3>
                <p className="mt-2 text-xs text-muted-foreground">
                  {job.location || "Location not listed"}
                  {job.workMode ? ` · ${job.workMode}` : ""}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {job.reasons.map((reason) => (
                    <span
                      key={reason}
                      className="rounded-md bg-acid/8 px-2 py-1 text-[11px] text-acid"
                    >
                      {reason}
                    </span>
                  ))}
                </div>
                {job.unknowns.length > 0 && (
                  <p className="mt-4 text-xs leading-5 text-muted-foreground">
                    To verify · {job.unknowns.join(" · ")}
                  </p>
                )}
              </article>
            ))}
          </div>
          {feed.data.jobs.length === 0 && (
            <div className="rounded-xl border border-dashed border-border p-10 text-center">
              <FileSearch className="mx-auto size-9 text-acid" />
              <p className="mt-4 text-lg">{state?.title}</p>
              <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
                {state?.copy}
              </p>
              <Link
                href="/jobs/intake"
                className="mt-5 inline-block text-sm text-acid underline underline-offset-4"
              >
                Bring a job description
              </Link>
            </div>
          )}
        </section>
      )}
      {feed.data?.jobs.length ? (
        <details className="border-t border-border pt-3 text-xs text-muted-foreground">
          <summary className="w-fit cursor-pointer py-2">
            How scores work
          </summary>
          <p className="mt-1 max-w-xl leading-6">
            Preference scores reflect role, skill, location, and experience
            alignment. Use Resume fit to compare a job with your resume.
          </p>
        </details>
      ) : null}
      <Dialog
        open={editing}
        onOpenChange={(open) => {
          if (!saving) setEditing(open);
        }}
      >
        <DialogContent className="sm:max-w-xl" showCloseButton={!saving}>
          <DialogHeader>
            <p className="ops-label text-acid">
              Personal signal / Configuration
            </p>
            <DialogTitle>Your direction. Your preferences.</DialogTitle>
            <DialogDescription>
              These choices change your feed immediately using the latest daily
              pool. Separate multiple values with commas.
            </DialogDescription>
          </DialogHeader>
          {preferences.isLoading ? (
            <p role="status">Loading preferences…</p>
          ) : preferences.error ? (
            <div role="alert">
              <p>{errorSummary(preferences.error)}</p>
              <Button onClick={() => void preferences.mutate()}>Retry</Button>
            </div>
          ) : (
            <form onSubmit={save} className="space-y-4">
              <div className="space-y-3">
                {[
                  [
                    "titles",
                    "Target roles",
                    preferences.data?.preferredTitles.join(", "),
                    "Frontend Engineer, Designer",
                  ],
                  [
                    "skills",
                    "Skills you want to use",
                    preferences.data?.preferredSkills.join(", "),
                    "React.js, TypeScript",
                  ],
                  [
                    "locations",
                    "Locations or Remote",
                    preferences.data?.preferredLocations.join(", "),
                    "London, Remote",
                  ],
                ].map(([name, label, value, placeholder]) => (
                  <label
                    key={name}
                    className="block text-xs text-muted-foreground"
                  >
                    {label}
                    <Input
                      className="mt-2"
                      name={name}
                      defaultValue={value}
                      placeholder={placeholder}
                      maxLength={2000}
                      disabled={saving}
                    />
                  </label>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-3">
                {[
                  [
                    "experienceMin",
                    "Experience from (years)",
                    preferences.data?.experienceMinYears,
                  ],
                  [
                    "experienceMax",
                    "Experience up to (years)",
                    preferences.data?.experienceMaxYears,
                  ],
                  [
                    "salaryMin",
                    "Minimum annual salary",
                    preferences.data?.salaryMin,
                  ],
                  [
                    "salaryMax",
                    "Maximum annual salary",
                    preferences.data?.salaryMax,
                  ],
                ].map(([name, label, value]) => (
                  <label key={name} className="text-xs text-muted-foreground">
                    {label}
                    <Input
                      className="mt-2"
                      type="number"
                      min="0"
                      step="any"
                      name={String(name)}
                      defaultValue={value ?? ""}
                      disabled={saving}
                    />
                  </label>
                ))}
              </div>
              <label className="block text-xs text-muted-foreground">
                Salary currency
                <Input
                  className="mt-2"
                  name="currency"
                  defaultValue={preferences.data?.salaryCurrency ?? "INR"}
                  maxLength={10}
                  disabled={saving}
                />
              </label>
              <p className="text-xs leading-5 text-muted-foreground">
                Salary is shown as a review signal when comparable annual pay is
                available. Remote roles may still have country restrictions.
              </p>
              {saveError && (
                <p role="alert" className="text-sm text-coral">
                  {saveError}
                </p>
              )}
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  disabled={saving}
                  onClick={() => setEditing(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving preferences…" : "Save preferences"}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
