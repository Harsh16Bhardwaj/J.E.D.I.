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
  EyeOff,
  RefreshCw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

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
import { prepareApplicationMove, type ApplicationMoveAttempt } from "@/lib/application-move";

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
    <div role="alert" className="mt-4 rounded-lg border border-coral/40 bg-coral/5 p-4">
      <p className="text-sm font-bold text-coral">{errorSummary(error)}</p>
      {isApiError(error) && error.requestId && (
        <details className="mt-3 text-xs text-muted-foreground">
          <summary className="cursor-pointer font-mono uppercase tracking-wider">
            Technical details
          </summary>
          <p className="mt-2 break-all font-mono">Request ID: {error.requestId}</p>
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
  const hasApplied = !["NOT_STARTED", "PREPARING"].includes(job.applicationStatus);
  const score = prediction?.rankingScore ?? prediction?.jediPreferenceScore ?? null;

  return (
    <BrutalCard className={`group overflow-hidden border-l-4 p-0 transition hover:-translate-y-0.5 hover:shadow-[5px_5px_0_var(--foreground)] ${hasApplied ? "border-l-acid" : isViewed ? "border-l-purple" : "border-l-coral"}`}>
      <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_12rem]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {isBookmarked ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-purple/40 bg-purple/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-purple">
                <BookmarkCheck className="size-3" /> Bookmarked
              </span>
            ) : null}
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${isViewed ? "border-purple/35 bg-purple/10 text-purple" : "border-coral/35 bg-coral/10 text-coral"}`}>
              {isViewed ? <Eye className="size-3" /> : <EyeOff className="size-3" />}
              {isViewed ? "Viewed" : "Unseen"}
            </span>
            <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${hasApplied ? "border-acid/35 bg-acid/10 text-acid" : job.applicationStatus === "PREPARING" ? "border-purple/35 bg-purple/10 text-purple" : "border-border bg-raised text-muted-foreground"}`}>
              {hasApplied ? `Applied Â· ${label(job.applicationStatus)}` : label(job.applicationStatus)}
            </span>
            {prediction ? <span className="ops-label text-muted-foreground">Persisted rank #{prediction.rank}</span> : null}
          </div>

          <Link href={`/jobs/${job.id}`} className="mt-4 block w-fit max-w-full">
            <h2 className="truncate text-xl font-black uppercase tracking-tight transition-colors group-hover:text-acid sm:text-2xl">
              {job.roleTitle}
            </h2>
          </Link>
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-bold text-foreground">{job.companyName}</span>
            {job.location ? ` Â· ${job.location}` : ""}
            {job.workMode ? ` Â· ${label(job.workMode)}` : ""}
          </p>

          <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <span>{postedDaysAgo(job.batchCreatedAt)}</span>
            <span className="font-semibold text-acid">{formatCompensationLpa(job)}</span>
            {job.relevanceLabel ? <span>Preference: {label(job.relevanceLabel)}</span> : null}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-border pt-4 lg:block lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
          {prediction ? (
            <>
              <div>
                <p className="ops-label text-muted-foreground">Legacy preference</p>
                <p className="mt-1 text-4xl font-black tracking-[-0.06em]">
                  {score?.toFixed(1)}
                </p>
              </div>
              <div className="text-right lg:mt-5 lg:text-left">
                <p className="ops-label text-muted-foreground">Apply probability</p>
                <p className="mt-1 font-mono text-sm">
                  {probability(prediction.applyPreferenceProbability)}
                </p>
              </div>
            </>
          ) : (
            <p className="max-w-40 text-xs leading-5 text-muted-foreground">
              No successful ranking run has scored this job yet.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-raised/40 px-5 py-3">
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="cursor-pointer"
            disabled={marking || isViewed}
            onClick={onViewed}
          >
            {isViewed ? <Check /> : <Eye />}
            {marking ? "Saving..." : isViewed ? "Viewed" : "Mark viewed"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className={`cursor-pointer ${isBookmarked ? "text-purple" : ""}`}
            disabled={bookmarking}
            onClick={onBookmark}
          >
            <BookmarkCheck />
            {bookmarking ? "Saving..." : isBookmarked ? "Bookmarked" : "Bookmark"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="cursor-pointer hover:border-acid/40 hover:bg-acid/10"
            disabled={!canStart || starting}
            onClick={onStart}
          >
            <BriefcaseBusiness />
            {canStart ? "Start application" : label(job.applicationStatus)}
          </Button>
        </div>
        <Link href={`/jobs/${job.id}`} className="inline-flex min-h-9 cursor-pointer items-center gap-2 rounded-md px-3 text-sm font-medium hover:bg-raised hover:text-acid">
          Open detail <ArrowUpRight className="size-4" />
        </Link>
      </div>
    </BrutalCard>
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
  const advancedFilterCount = ["minScore", "viewed", "applied"].filter(key => searchParams.get(key)).length;
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
      (current) => current ? {
        ...current,
        items: current.items.map((item) => item.id === job.id ? { ...item, reviewStatus: "VIEWED" } : item),
      } : current,
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
        const items = bookmarkedOnly && bookmarked
          ? current.items.filter((item) => item.id !== job.id)
          : current.items.map((item) => item.id === job.id ? { ...item, reviewStatus: bookmarked ? "VIEWED" : "SAVED" } : item);
        return {
          ...current,
          items,
          total: bookmarkedOnly && bookmarked ? Math.max(0, current.total - 1) : current.total,
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
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Jobs</h1>
          <p className="mt-1 text-sm text-muted-foreground">Scores use the Legacy group profile.</p>
        </div>
        <Link href="/jobs/intake" className={buttonVariants({ variant: "outline" })}>Bring a job</Link>
      </header>

      <section aria-label="Job filters" className="space-y-3 rounded-xl border border-border bg-card p-3 sm:p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[12rem] flex-1">
            <Search aria-hidden="true" className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={event => setSearch(event.target.value)}
              aria-label="Search jobs" placeholder="Search job titles or companies" className="min-h-10 bg-background pl-9" />
          </div>
          <select aria-label="Sort jobs" className="min-h-10 rounded-lg border border-border bg-background px-3 text-sm"
            value={searchParams.get("sort") ?? "recent"} onChange={event => updateParams({ sort: event.target.value === "recent" ? null : event.target.value, page: 1 })}>
            <option value="recent">Newest</option>
            <option value="score">Best match</option>
          </select>
          {hasFilters && <Button variant="ghost" className="min-h-10" onClick={() => {
            setSearch("");
            router.replace(pathname, { scroll: false });
          }}><X className="size-4" /> Clear filters</Button>}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant={!bookmarkedOnly ? "secondary" : "ghost"} aria-pressed={!bookmarkedOnly}
            onClick={() => updateParams({ reviewStatus: null, page: 1 })}>All jobs</Button>
          <Button variant={bookmarkedOnly ? "secondary" : "ghost"} aria-pressed={bookmarkedOnly}
            onClick={() => updateParams({ reviewStatus: "SAVED", viewed: null, page: 1 })}>
            <BookmarkCheck className="size-4" /> Bookmarked
          </Button>
          <span className="ml-auto text-xs text-muted-foreground">{jobs.data ? `${jobs.data.total} results` : ""}</span>
        </div>

        <details className="border-t border-border pt-2">
          <summary className="w-fit cursor-pointer rounded px-2 py-1 text-sm focus-visible:outline-2 focus-visible:outline-ring">
            <SlidersHorizontal aria-hidden="true" className="mr-2 inline size-4" /> More filters
            {advancedFilterCount > 0 && <span className="ml-2 text-acid">({advancedFilterCount} active)</span>}
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {[
              { label: "Minimum score", key: "minScore", choices: [["", "Any score"], ["60", "60+"], ["75", "75+"]] },
              { label: "Review", key: "viewed", choices: [["", "Any"], ["false", "Unseen"], ["true", "Viewed"]] },
              { label: "Application", key: "applied", choices: [["", "Any"], ["false", "Not applied"], ["true", "Applied"]] },
            ].map(({ label, key, choices }) => {
              const value = searchParams.get(key) ?? "";
              return <label key={key} className="grid gap-1.5 text-xs text-muted-foreground">
                {label}
                <select className="min-h-10 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground"
                  value={value} onChange={event => updateParams({
                    [key]: event.target.value,
                    ...(key === "viewed" ? { reviewStatus: null } : {}),
                    page: 1,
                  })}>
                  {!choices.some(([option]) => option === value) && <option value={value}>{value}</option>}
                  {choices.map(([option, name]) => <option key={option} value={option}>{name}</option>)}
                </select>
              </label>;
            })}
          </div>
        </details>
      </section>

      {jobs.isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-64 rounded-xl bg-raised" />)}
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
        <section className="space-y-3" aria-busy={jobs.isValidating}>
          {jobs.isValidating && (
            <p className="ops-label text-muted-foreground">Refreshing jobs...</p>
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
          <h2 className="mt-5 text-2xl font-black uppercase">No matching jobs</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Try a different search or clear the filters.
          </p>
        </BrutalCard>
      )}

      <div className="flex items-center justify-between">
        <Button variant="outline" disabled={page <= 1} onClick={() => updateParams({ page: page - 1 })}>
          <ArrowLeft /> Previous
        </Button>
        <p className="ops-label text-muted-foreground">Page {page} of {pages}</p>
        <Button variant="outline" disabled={page >= pages} onClick={() => updateParams({ page: page + 1 })}>
          Next <ArrowRight />
        </Button>
      </div>

      <Dialog
        open={Boolean(selectedJob)}
        onOpenChange={(open) => {
          if (!open && !starting) setSelectedJob(undefined);
        }}
      >
        <DialogContent showCloseButton={!starting} className="border border-border sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-xl font-black uppercase">Start preparing?</DialogTitle>
            <DialogDescription>
              {selectedJob
                ? `${selectedJob.roleTitle} at ${selectedJob.companyName} will move into your Preparing stage.`
                : "This job will enter the application funnel."}
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-border bg-raised/50 p-4 text-sm leading-6 text-muted-foreground">
            This records a private status event for your member account. It does not submit an application to the employer.
          </div>
          {Boolean(actionError) && <ErrorDetails error={actionError} />}
          <DialogFooter>
            <Button variant="outline" disabled={starting} onClick={() => setSelectedJob(undefined)}>Cancel</Button>
            <Button disabled={starting} onClick={() => void startApplication()}>
              <BriefcaseBusiness /> {starting ? "Savingâ€¦" : "Move to preparing"}
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
