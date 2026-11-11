"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookmarkCheck,
  BriefcaseBusiness,
  Check,
  Eye,
  RefreshCw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { CompanyMark } from "@/components/company-mark";
import { BrutalCard } from "@/components/brutal-card";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  apiRequest,
  errorSummary,
  isApiError,
  type ApplicationEventResult,
  type JobListItem,
  type JobPage,
  type JobStateResult,
} from "@/lib/api";
import { formatCompensationLpa, postedDaysAgo } from "@/lib/job-display";
import {
  prepareApplicationMove,
  type ApplicationMoveAttempt,
} from "@/lib/application-move";

const PAGE_SIZE = 20;

function label(value: string) {
  return value.toLowerCase().replaceAll("_", " ");
}

function probability(value: number) {
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function ErrorDetails({ error }: { error: unknown }) {
  return (
    <div
      role="alert"
      className="mt-4 rounded-lg border border-coral/40 bg-coral/5 p-4"
    >
      <p className="text-sm font-bold text-coral">{errorSummary(error)}</p>
      {isApiError(error) && error.requestId && (
        <details className="mt-3 text-xs text-muted-foreground">
          <summary className="cursor-pointer font-mono uppercase tracking-wider">
            Technical details
          </summary>
          <p className="mt-2 break-all font-mono">
            Request ID: {error.requestId}
          </p>
        </details>
      )}
    </div>
  );
}

function JobCard({
  job,
  marking,
  bookmarking,
  starting,
  onViewed,
  onBookmark,
  onStart,
}: {
  job: JobListItem;
  marking: boolean;
  bookmarking: boolean;
  starting: boolean;
  onViewed: () => void;
  onBookmark: () => void;
  onStart: () => void;
}) {
  const prediction = job.latestPrediction;
  const canStart = job.applicationStatus === "NOT_STARTED";
  const isViewed = job.reviewStatus !== "NEW";
  const isBookmarked = job.reviewStatus === "SAVED";
  const score =
    prediction?.rankingScore ?? prediction?.jediPreferenceScore ?? null;

  return (
    <article className={`catalog-job ${isBookmarked ? "is-saved" : ""}`}>
      <div className="catalog-job-main">
        <CompanyMark name={job.companyName} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <p className="font-medium text-muted-foreground">
              {job.companyName}
            </p>
            {!isViewed && (
              <span className="inline-flex items-center gap-1 text-[var(--info)]">
                <span className="size-1.5 rounded-full bg-[var(--info)]" />
                Unseen
              </span>
            )}
            {job.applicationStatus !== "NOT_STARTED" && (
              <span className="text-primary">
                {label(job.applicationStatus)}
              </span>
            )}
          </div>
          <Link href={`/jobs/${job.id}`} className="mt-1.5 block w-fit">
            <h2 className="text-xl font-semibold leading-snug tracking-tight hover:text-primary">
              {job.roleTitle}
            </h2>
          </Link>
          <p className="mt-2 text-xs text-muted-foreground">
            {job.location || "Location not listed"}
            {job.workMode &&
            job.location?.toLowerCase() !== job.workMode.toLowerCase()
              ? ` · ${label(job.workMode)}`
              : ""}
          </p>
          <p
            className={`mt-3 text-sm font-semibold ${job.salaryMin == null && job.salaryMax == null ? "text-muted-foreground" : "text-[var(--success)]"}`}
          >
            {formatCompensationLpa(job)}
          </p>
        </div>
        <div className="catalog-score">
          {prediction ? (
            <>
              <strong>{score === null ? "—" : score.toFixed(1)}</strong>
              <span>Legacy score /100</span>
              <span className="mt-2">
                {probability(prediction.applyPreferenceProbability)} apply
                signal
              </span>
            </>
          ) : (
            <span>Unscored</span>
          )}
        </div>
      </div>
      <footer className="catalog-job-actions">
        <span className="mr-auto text-[11px] text-muted-foreground">
          {postedDaysAgo(job.batchCreatedAt).replace("Posted", "Imported")}
        </span>
        <Button
          variant="ghost"
          size="sm"
          disabled={marking || isViewed}
          onClick={onViewed}
        >
          {isViewed ? <Check /> : <Eye />}
          {marking ? "Saving…" : isViewed ? "Viewed" : "Mark viewed"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={isBookmarked}
          disabled={bookmarking}
          onClick={onBookmark}
          className={isBookmarked ? "text-purple" : ""}
        >
          <BookmarkCheck />
          {bookmarking ? "Saving…" : isBookmarked ? "Bookmarked" : "Bookmark"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!canStart || starting}
          onClick={onStart}
        >
          <BriefcaseBusiness />
          {canStart ? "Start application" : label(job.applicationStatus)}
        </Button>
        <Link
          href={`/jobs/${job.id}`}
          aria-label={`Open ${job.roleTitle} at ${job.companyName}`}
          className="grid size-9 place-items-center rounded-md hover:bg-muted focus-visible:outline-2 focus-visible:outline-primary"
        >
          <ArrowUpRight className="size-4" />
        </Link>
      </footer>
    </article>
  );
}

function JobsWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { mutate: mutateGlobal } = useSWRConfig();
  const [search, setSearch] = useState(searchParams.get("search") ?? "");
  const [markingId, setMarkingId] = useState<string>();
  const [bookmarkingId, setBookmarkingId] = useState<string>();
  const [selectedJob, setSelectedJob] = useState<JobListItem>();
  const startAttempt = useRef<ApplicationMoveAttempt>(undefined);
  const [starting, setStarting] = useState(false);
  const [actionError, setActionError] = useState<unknown>();

  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);
  const query = useMemo(() => {
    const result = new URLSearchParams(searchParams.toString());
    result.set("page", String(page));
    result.set("pageSize", String(PAGE_SIZE));
    return result.toString();
  }, [page, searchParams]);
  const jobs = useSWR<JobPage>(`/api/jobs?${query}`);
  const pages = Math.max(1, Math.ceil((jobs.data?.total ?? 0) / PAGE_SIZE));
  const currentSearch = searchParams.get("search") ?? "";
  const hasFilters = Boolean(
    currentSearch ||
      searchParams.get("viewed") ||
      searchParams.get("applied") ||
      searchParams.get("minScore") ||
      searchParams.get("reviewStatus") ||
      searchParams.get("sort"),
  );
  const bookmarkedOnly = searchParams.get("reviewStatus") === "SAVED";

  function updateParams(values: Record<string, string | number | null>) {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(values)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, String(value));
    }
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const value = search.trim();
      if (value === currentSearch) return;
      const next = new URLSearchParams(searchParams.toString());
      if (value) next.set("search", value);
      else next.delete("search");
      next.set("page", "1");
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [currentSearch, pathname, router, search, searchParams]);

  async function invalidate(jobId: string) {
    await mutateGlobal(
      (key) =>
        typeof key === "string" &&
        (key.startsWith("/api/jobs") ||
          key.startsWith("/api/applications") ||
          key.startsWith("/api/dashboard") ||
          key === `/api/jobs/${jobId}`),
      undefined,
      { revalidate: true },
    );
  }

  async function markViewed(job: JobListItem) {
    if (markingId) return;
    setMarkingId(job.id);
    const previous = jobs.data;
    await jobs.mutate(
      (current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) =>
                item.id === job.id ? { ...item, reviewStatus: "VIEWED" } : item,
              ),
            }
          : current,
      { revalidate: false },
    );
    try {
      await apiRequest<JobStateResult>(`/api/jobs/${job.id}/view`, {
        method: "POST",
      });
      toast.success("Job marked as viewed.");
      await mutateGlobal(
        (key) => typeof key === "string" && key.startsWith("/api/dashboard"),
        undefined,
        { revalidate: true },
      );
    } catch (error) {
      await jobs.mutate(previous, { revalidate: false });
      toast.error(errorSummary(error));
    } finally {
      setMarkingId(undefined);
    }
  }

  async function toggleBookmark(job: JobListItem) {
    if (bookmarkingId) return;
    setBookmarkingId(job.id);
    const bookmarked = job.reviewStatus === "SAVED";
    const previous = jobs.data;
    await jobs.mutate(
      (current) => {
        if (!current) return current;
        const items =
          bookmarkedOnly && bookmarked
            ? current.items.filter((item) => item.id !== job.id)
            : current.items.map((item) =>
                item.id === job.id
                  ? { ...item, reviewStatus: bookmarked ? "VIEWED" : "SAVED" }
                  : item,
              );
        return {
          ...current,
          items,
          total:
            bookmarkedOnly && bookmarked
              ? Math.max(0, current.total - 1)
              : current.total,
        };
      },
      { revalidate: false },
    );
    try {
      await apiRequest<JobStateResult>(`/api/jobs/${job.id}/state`, {
        method: "PATCH",
        body: JSON.stringify({ reviewStatus: bookmarked ? "VIEWED" : "SAVED" }),
      });
      toast.success(bookmarked ? "Bookmark removed." : "Job bookmarked.");
      await mutateGlobal(
        (key) => typeof key === "string" && key.startsWith("/api/dashboard"),
        undefined,
        { revalidate: true },
      );
    } catch (error) {
      await jobs.mutate(previous, { revalidate: false });
      toast.error(errorSummary(error));
    } finally {
      setBookmarkingId(undefined);
    }
  }

  async function startApplication() {
    if (!selectedJob || starting) return;
    setStarting(true);
    setActionError(undefined);
    const request = prepareApplicationMove(
      { status: selectedJob.applicationStatus, updatedAt: null },
      "PREPARING",
      "Application preparation started from the ranked jobs queue.",
      startAttempt.current,
    );
    startAttempt.current = request.attempt;
    try {
      await apiRequest<ApplicationEventResult>(
        `/api/jobs/${selectedJob.id}/application-events`,
        {
          method: "POST",
          body: request.body,
          signal: AbortSignal.timeout(15_000),
        },
      );
      toast.success("Application moved to preparing.");
      await invalidate(selectedJob.id);
      setSelectedJob(undefined);
    } catch (error) {
      setActionError(error);
      toast.error(errorSummary(error));
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          Jobs{" "}
          <span className="ml-2 align-middle font-mono text-sm font-normal text-muted-foreground">
            {jobs.data?.total ?? "—"}
          </span>
        </h1>
        <Link
          href="/jobs/intake"
          className={buttonVariants({ variant: "outline" })}
        >
          Bring a job <ArrowUpRight className="size-4" />
        </Link>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex w-fit gap-1 rounded-xl border border-border bg-card p-1.5 shadow-sm">
          <button
            type="button"
            className={`min-h-10 cursor-pointer rounded-lg border px-5 text-sm font-bold transition ${!bookmarkedOnly ? "border-acid bg-acid text-background shadow-[3px_3px_0_var(--foreground)]" : "border-transparent text-muted-foreground hover:bg-raised hover:text-foreground"}`}
            aria-pressed={!bookmarkedOnly}
            onClick={() => updateParams({ reviewStatus: null, page: 1 })}
          >
            All jobs
          </button>
          <button
            type="button"
            aria-pressed={bookmarkedOnly}
            className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border px-5 text-sm font-bold transition ${bookmarkedOnly ? "border-purple bg-purple text-background shadow-[3px_3px_0_var(--foreground)]" : "border-transparent text-muted-foreground hover:bg-raised hover:text-foreground"}`}
            onClick={() =>
              updateParams({ reviewStatus: "SAVED", viewed: null, page: 1 })
            }
          >
            <BookmarkCheck className="size-4" /> Bookmarked
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-0 flex-[1_1_16rem]">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="Search jobs"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Company or job title"
              className="pl-10"
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Sort
            <select
              className="min-h-10 rounded-md border border-border bg-background px-3 text-foreground"
              value={searchParams.get("sort") ?? "recent"}
              onChange={(event) =>
                updateParams({ sort: event.target.value, page: 1 })
              }
            >
              <option value="recent">Newest</option>
              <option value="score">Best match</option>
            </select>
          </label>
          {hasFilters && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearch("");
                router.replace(pathname, { scroll: false });
              }}
            >
              <X className="size-4" />
              Clear
            </Button>
          )}
        </div>
        <details
          className="mt-3 border-t border-border pt-3"
          open={
            Boolean(
              searchParams.get("minScore") ||
                searchParams.get("viewed") ||
                searchParams.get("applied"),
            ) || undefined
          }
        >
          <summary className="flex w-fit cursor-pointer items-center gap-2 text-xs font-medium">
            <SlidersHorizontal className="size-3.5" />
            Filters
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {[
              {
                label: "Minimum score",
                key: "minScore",
                choices: [
                  ["", "Any score"],
                  ["60", "60+"],
                  ["75", "75+"],
                ],
              },
              {
                label: "Review",
                key: "viewed",
                choices: [
                  ["", "All jobs"],
                  ["false", "Unseen"],
                  ["true", "Viewed"],
                ],
              },
              {
                label: "Application",
                key: "applied",
                choices: [
                  ["", "All stages"],
                  ["false", "Not applied"],
                  ["true", "Applied"],
                ],
              },
            ].map((group) => {
              const current = searchParams.get(group.key) ?? "";
              return (
                <label
                  key={group.key}
                  className="flex flex-col gap-1.5 text-xs text-muted-foreground"
                >
                  {group.label}
                  <select
                    className="min-h-10 min-w-0 rounded-md border border-border bg-background px-3 text-foreground"
                    aria-label={group.label}
                    value={current}
                    onChange={(event) =>
                      updateParams({
                        [group.key]: event.target.value,
                        ...(group.key === "viewed"
                          ? { reviewStatus: null }
                          : {}),
                        page: 1,
                      })
                    }
                  >
                    {!group.choices.some(([value]) => value === current) && (
                      <option value={current}>{current}</option>
                    )}
                    {group.choices.map(([value, text]) => (
                      <option key={value} value={value}>
                        {text}
                      </option>
                    ))}
                  </select>
                </label>
              );
            })}
          </div>
        </details>
      </div>

      {jobs.isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((item) => (
            <Skeleton key={item} className="h-44 rounded-xl bg-raised" />
          ))}
        </div>
      ) : jobs.error ? (
        <BrutalCard className="border-coral/40 py-10 text-center">
          <p className="ops-label text-coral">Job queue unavailable</p>
          <ErrorDetails error={jobs.error} />
          <Button className="mt-5" onClick={() => void jobs.mutate()}>
            <RefreshCw /> Retry
          </Button>
        </BrutalCard>
      ) : jobs.data?.items.length ? (
        <section className="jobs-listing-stack" aria-busy={jobs.isValidating}>
          {jobs.isValidating && (
            <p className="ops-label text-muted-foreground">
              Refreshing jobs...
            </p>
          )}
          {jobs.data.items.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              marking={markingId === job.id}
              bookmarking={bookmarkingId === job.id}
              starting={starting && selectedJob?.id === job.id}
              onViewed={() => void markViewed(job)}
              onBookmark={() => void toggleBookmark(job)}
              onStart={() => {
                setActionError(undefined);
                startAttempt.current = undefined;
                setSelectedJob(job);
              }}
            />
          ))}
        </section>
      ) : (
        <BrutalCard className="py-16 text-center">
          <Search className="mx-auto size-8 text-muted-foreground" />
          <h2 className="mt-5 text-2xl font-black uppercase">
            No matching jobs
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Try another search or clear your filters.
          </p>
        </BrutalCard>
      )}

      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          disabled={page <= 1}
          onClick={() => updateParams({ page: page - 1 })}
        >
          <ArrowLeft /> Previous
        </Button>
        <p className="ops-label text-muted-foreground">
          Page {page} of {pages}
        </p>
        <Button
          variant="outline"
          disabled={page >= pages}
          onClick={() => updateParams({ page: page + 1 })}
        >
          Next <ArrowRight />
        </Button>
      </div>

      <Dialog
        open={Boolean(selectedJob)}
        onOpenChange={(open) => {
          if (!open && !starting) setSelectedJob(undefined);
        }}
      >
        <DialogContent
          showCloseButton={!starting}
          className="border border-border sm:max-w-lg"
        >
          <DialogHeader>
            <DialogTitle className="text-xl font-black uppercase">
              Start preparing?
            </DialogTitle>
            <DialogDescription>
              {selectedJob
                ? `${selectedJob.roleTitle} at ${selectedJob.companyName} will move into your Preparing stage.`
                : "This job will enter the application funnel."}
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-border bg-raised/50 p-4 text-sm leading-6 text-muted-foreground">
            This records a private status event for your member account. It does
            not submit an application to the employer.
          </div>
          {Boolean(actionError) && <ErrorDetails error={actionError} />}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={starting}
              onClick={() => setSelectedJob(undefined)}
            >
              Cancel
            </Button>
            <Button disabled={starting} onClick={() => void startApplication()}>
              <BriefcaseBusiness /> {starting ? "Saving…" : "Move to preparing"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function JobsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[70vh] rounded-xl bg-raised" />}>
      <JobsWorkspace />
    </Suspense>
  );
}
