"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
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
              {hasApplied ? `Applied · ${label(job.applicationStatus)}` : label(job.applicationStatus)}
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
            {job.location ? ` · ${job.location}` : ""}
            {job.workMode ? ` · ${label(job.workMode)}` : ""}
          </p>

          <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <span>Added {new Date(job.createdAt).toLocaleDateString()}</span>
            {job.relevanceLabel ? <span>Preference: {label(job.relevanceLabel)}</span> : null}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-border pt-4 lg:block lg:border-l lg:border-t-0 lg:pl-5 lg:pt-0">
          {prediction ? (
            <>
              <div>
                <p className="ops-label text-muted-foreground">Preference</p>
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
    try {
      await apiRequest<ApplicationEventResult>(
        `/api/jobs/${selectedJob.id}/application-events`,
        {
          method: "POST",
          body: JSON.stringify({
            applicationStatus: "PREPARING",
            notes: "Application preparation started from the ranked jobs queue.",
          }),
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
      <header className="relative overflow-hidden rounded-xl border border-acid/25 bg-gradient-to-br from-acid/15 via-card to-purple/10 p-6 sm:p-8">
        <div className="absolute -right-12 -top-16 size-48 rounded-full bg-acid/10 blur-3xl" />
        <p className="ops-label text-acid">Opportunity workspace</p>
        <div className="relative mt-3 flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div>
            <h1 className="text-4xl font-black uppercase tracking-[-0.05em] sm:text-6xl">Jobs</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
              Find the strongest matches, see what you have reviewed, and move promising work into your private application pipeline.
            </p>
          </div>
          <div className="flex gap-2">
            <div className="min-w-24 rounded-lg border border-border bg-background/70 px-4 py-3">
              <p className="text-2xl font-black">{jobs.data?.total ?? "--"}</p>
              <p className="ops-label mt-1 text-muted-foreground">Results</p>
            </div>
            <div className="min-w-24 rounded-lg border border-border bg-background/70 px-4 py-3">
              <p className="text-2xl font-black">{page}/{pages}</p>
              <p className="ops-label mt-1 text-muted-foreground">Page</p>
            </div>
          </div>
        </div>
      </header>

      <div className="inline-flex w-fit gap-1 rounded-xl border border-border bg-card p-1.5 shadow-sm">
        <button
          type="button"
          className={`min-h-10 cursor-pointer rounded-lg border px-5 text-sm font-bold transition ${!bookmarkedOnly ? "border-acid bg-acid text-background shadow-[3px_3px_0_var(--foreground)]" : "border-transparent text-muted-foreground hover:bg-raised hover:text-foreground"}`}
          onClick={() => updateParams({ reviewStatus: null, page: 1 })}
        >
          All jobs
        </button>
        <button
          type="button"
          className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border px-5 text-sm font-bold transition ${bookmarkedOnly ? "border-purple bg-purple text-background shadow-[3px_3px_0_var(--foreground)]" : "border-transparent text-muted-foreground hover:bg-raised hover:text-foreground"}`}
          onClick={() => updateParams({ reviewStatus: "SAVED", viewed: null, page: 1 })}
        >
          <BookmarkCheck className="size-4" /> Bookmarked
        </button>
      </div>

      <BrutalCard className="space-y-5 border-purple/25 bg-gradient-to-r from-card to-purple/5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="size-4 text-purple" />
            <p className="ops-label">Find the right jobs</p>
          </div>
          {hasFilters ? (
            <Button
              variant="ghost"
              size="sm"
              className="cursor-pointer text-muted-foreground hover:text-coral"
              onClick={() => {
                setSearch("");
                router.replace(pathname, { scroll: false });
              }}
            >
              <X className="size-4" /> Clear
            </Button>
          ) : null}
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search company or job title..."
            className="min-h-12 border-2 bg-background pl-10 pr-24"
          />
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
            Auto search
          </span>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Order", key: "sort", choices: [["recent", "Newest"], ["score", "Best match"]] },
            { label: "Minimum score", key: "minScore", choices: [["", "Any"], ["60", "60+"], ["75", "75+"]] },
            { label: "Review", key: "viewed", choices: [["", "All"], ["false", "Unseen"], ["true", "Viewed"]] },
            { label: "Application", key: "applied", choices: [["", "All"], ["false", "Not applied"], ["true", "Applied"]] },
          ].map((group) => (
            <div key={group.key}>
              <p className="ops-label mb-2 text-muted-foreground">{group.label}</p>
              <div className="flex flex-wrap gap-1 rounded-lg border border-border bg-background/70 p-1">
                {group.choices.map(([value, choiceLabel]) => {
                  const current = searchParams.get(group.key) ?? (group.key === "sort" ? "recent" : "");
                  const active = current === value;
                  return (
                    <button
                      key={value || "all"}
                      type="button"
                      aria-pressed={active}
                      className={`min-h-9 flex-1 cursor-pointer rounded-md px-2 text-xs font-medium transition ${active ? "bg-foreground text-background shadow-sm" : "text-muted-foreground hover:bg-raised hover:text-foreground"}`}
                      onClick={() => updateParams({
                        [group.key]: value,
                        ...(group.key === "viewed" ? { reviewStatus: null } : {}),
                        page: 1,
                      })}
                    >
                      {choiceLabel}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </BrutalCard>

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
            Adjust the filters, or import and rank another batch.
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
