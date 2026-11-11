"use client";

import { useState } from "react";
import Link from "next/link";
import { ScoreRing } from "@/components/score-ring";
import { ApplicationPipeline } from "@/components/feed-insights";
import {
  ArrowUpRight,
  Boxes,
  BriefcaseBusiness,
  CheckCircle2,
  DatabaseZap,
  EyeOff,
  RefreshCw,
  Server,
  Trophy,
  X,
} from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  apiRequest,
  errorSummary,
  timedGet,
  type ApplicationAction,
  type ApplicationSummary,
  type BatchPage,
  type DashboardFeed,
  type DashboardJob,
  type Health,
  type TimedResult,
  type User,
} from "@/lib/api";
import { formatCompensationLpa, postedDaysAgo } from "@/lib/job-display";

type Period = "daily" | "weekly" | "overall";

function HealthLine({
  label,
  icon: Icon,
  result,
  error,
}: {
  label: string;
  icon: typeof Server;
  result?: TimedResult<Health>;
  error?: unknown;
}) {
  return (
    <div className="flex items-center justify-between gap-5 rounded-xl border border-border bg-card px-4 py-3">
      <div className="flex items-center gap-3">
        <Icon className="size-4 text-muted-foreground" />
        <div>
          <p className="text-sm font-medium">{label}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {result
              ? `${result.latencyMs}ms / ${new Date(result.checkedAt).toLocaleTimeString()}`
              : errorSummary(error)}
          </p>
        </div>
      </div>
      <span
        className={`size-2 rounded-full ${result ? "bg-acid" : "bg-coral"}`}
      />
    </div>
  );
}

function SectionHeading({
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col justify-between gap-4 border-b border-border pb-4 sm:flex-row sm:items-end">
      <div>
        <h2 className="text-xl font-semibold">{title}</h2>
        {description ? <span className="sr-only">{description}</span> : null}
      </div>
      {action}
    </div>
  );
}

function readableStatus(value: string) {
  return value.toLowerCase().replaceAll("_", " ");
}

function JobCard({ job }: { job: DashboardJob }) {
  const score = job.jediPreferenceScore ?? job.rankingScore;
  return (
    <Link
      href={`/jobs/${job.id}`}
      aria-label={`Open ${job.roleTitle} at ${job.companyName}`}
      className="feed-card group"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="company-stamp" aria-hidden="true">
            {job.companyName.trim().charAt(0).toUpperCase() || "J"}
          </span>
          <p className="truncate text-sm font-semibold text-purple">
            {job.companyName}
          </p>
        </div>
        <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
      </div>
      <h3 className="my-4 line-clamp-2 text-xl font-bold leading-tight tracking-tight group-hover:text-primary">
        {job.roleTitle}
      </h3>
      <p className="text-xs text-muted-foreground">
        {job.location || "Location unspecified"}
        {job.workMode ? ` · ${readableStatus(job.workMode)}` : ""}
      </p>
      <div className="mt-4 flex items-end justify-between gap-3 border-t border-border pt-4">
        <div className="min-w-0">
          <p className="text-lg font-semibold text-primary">
            {formatCompensationLpa(job)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {[job.employmentType, job.seniority]
              .filter(Boolean)
              .map((value) => readableStatus(value!))
              .join(" · ")}
          </p>
          <p className="mt-3 text-[11px] text-muted-foreground">
            {job.postedAt
              ? postedDaysAgo(job.postedAt)
              : postedDaysAgo(job.batchCreatedAt).replace("Posted", "Imported")}
          </p>
        </div>
        <div className="shrink-0 text-center">
          <ScoreRing score={score} />
          <span className="text-[10px] text-muted-foreground">
            Shared preference
          </span>
        </div>
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const [period, setPeriod] = useState<Period>("daily");
  const [fresh, setFresh] = useState(false);
  const [completingActionId, setCompletingActionId] = useState<string>();
  const { mutate: mutateGlobal } = useSWRConfig();
  const session = useSWR<User>("/api/auth/session");
  const live = useSWR<TimedResult<Health>>(
    session.data?.isGroupOwner ? "/health/live" : null,
    timedGet,
    {
      refreshInterval: 30_000,
    },
  );
  const ready = useSWR<TimedResult<Health>>(
    session.data?.isGroupOwner ? "/health/ready" : null,
    timedGet,
    {
      refreshInterval: 30_000,
    },
  );
  const batches = useSWR<BatchPage>(
    session.data?.isGroupOwner ? "/api/batches?page=1&pageSize=5" : null,
    {
      refreshInterval: 10_000,
      revalidateOnFocus: true,
    },
  );
  const applicationActions = useSWR<ApplicationSummary>(
    "/api/applications/summary",
  );
  const query = new URLSearchParams({ leaderboardPeriod: period });
  if (fresh) query.set("fresh", "true");
  const feed = useSWR<DashboardFeed>(`/api/dashboard?${query}`, {
    refreshInterval: 10_000,
    revalidateOnFocus: true,
  });

  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const userName = session.data?.email.split("@")[0] ?? "there";
  const applicationCount = Object.values(
    applicationActions.data?.statusCounts ?? {},
  ).reduce((total, count) => total + count, 0);
  const leaderboardTitle =
    period === "daily"
      ? "Today's top 10"
      : period === "weekly"
        ? "This week's top 10"
        : "All-time top 10";

  async function completeApplicationAction(action: ApplicationAction) {
    if (completingActionId) return;
    setCompletingActionId(action.jobId);
    try {
      await apiRequest(`/api/jobs/${action.jobId}/application`, {
        method: "PATCH",
        body: JSON.stringify({
          nextAction: null,
          nextActionDueAt: null,
          expectedUpdatedAt: action.applicationUpdatedAt,
        }),
      });
      toast.success("Application task completed.");
      await mutateGlobal(
        (key) => typeof key === "string" && key.startsWith("/api/applications"),
        undefined,
        { revalidate: true },
      );
    } catch (error) {
      toast.error(errorSummary(error));
    } finally {
      setCompletingActionId(undefined);
    }
  }

  return (
    <div className="space-y-7">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-serif text-3xl tracking-tight">
          <span suppressHydrationWarning>{greeting}</span>, {userName}
          <span className="text-primary">.</span>
        </h1>
        <span
          className="text-xs text-muted-foreground"
          suppressHydrationWarning
        >
          {new Date().toLocaleDateString(undefined, {
            weekday: "long",
            month: "short",
            day: "numeric",
          })}
        </span>
      </header>

      <section>
        <SectionHeading
          eyebrow="New opportunities"
          title={
            feed.data?.jobFeedScope === "latest"
              ? "Latest jobs"
              : "Today's jobs"
          }
          description={
            feed.data?.jobFeedScope === "latest"
              ? "Latest available jobs, ordered by shared preference score."
              : "Today's jobs, ordered by shared preference score."
          }
          action={
            <div className="flex flex-wrap gap-2">
              <Button
                aria-pressed={fresh}
                variant={fresh ? "secondary" : "outline"}
                className={
                  fresh
                    ? "border border-acid bg-acid text-background shadow-[3px_3px_0_var(--foreground)]"
                    : "cursor-pointer hover:border-acid/50"
                }
                onClick={() => setFresh((value) => !value)}
              >
                <EyeOff className="size-4" /> Unseen only
              </Button>
            </div>
          }
        />
        {fresh ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-purple/30 bg-purple/10 px-4 py-3">
            <p className="text-sm">
              Showing <strong>{feed.data?.todayJobs.length ?? "..."}</strong>{" "}
              unseen jobs.
            </p>
            <Button
              variant="ghost"
              size="sm"
              className="cursor-pointer hover:text-coral"
              onClick={() => {
                setFresh(false);
              }}
            >
              <X className="size-4" /> Clear filters
            </Button>
          </div>
        ) : null}
        {feed.isLoading ? (
          <div className="mt-5 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {[0, 1, 2, 3, 4, 5].map((item) => (
              <Skeleton key={item} className="h-[16rem] rounded-xl bg-raised" />
            ))}
          </div>
        ) : feed.error ? (
          <BrutalCard className="mt-5 border-coral/35">
            <p className="text-sm text-coral">{errorSummary(feed.error)}</p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => void feed.mutate()}
            >
              Retry jobs
            </Button>
          </BrutalCard>
        ) : feed.data?.todayJobs.length ? (
          <>
            <div className="mt-5 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
              {feed.data.todayJobs.slice(0, 6).map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
            </div>
            <div className="mt-5 flex justify-end">
              <Link
                href="/jobs"
                className="flex min-h-11 items-center gap-2 text-sm font-medium text-muted-foreground hover:text-acid"
              >
                View all jobs <ArrowUpRight className="size-4" />
              </Link>
            </div>
          </>
        ) : (
          <BrutalCard className="mt-5 flex items-center justify-between gap-4">
            <div>
              <p className="font-medium">
                {fresh
                  ? "All available jobs have been viewed."
                  : "No jobs are available yet."}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {fresh
                  ? "Clear the unseen filter to see them again."
                  : "Check back for new opportunities or compare a job description."}
              </p>
            </div>
            {fresh ? (
              <Button
                variant="ghost"
                className="shrink-0"
                onClick={() => setFresh(false)}
              >
                Clear filter
              </Button>
            ) : (
              <Link
                href={
                  session.data?.isGroupOwner
                    ? "/batches?import=1"
                    : "/jobs/intake"
                }
                className="shrink-0 text-sm font-medium hover:text-acid"
              >
                {session.data?.isGroupOwner ? "Import batch" : "Compare a job"}
              </Link>
            )}
          </BrutalCard>
        )}
      </section>

      <section>
        <SectionHeading
          eyebrow="Private follow-through"
          title="Your applications"
          action={
            <Link
              href="/applications"
              className="flex min-h-11 items-center gap-2 text-xs text-muted-foreground hover:text-foreground"
            >
              Open pipeline <ArrowUpRight className="size-4" />
            </Link>
          }
        />
        {applicationActions.isLoading ? (
          <Skeleton className="mt-5 h-36 rounded-xl bg-raised" />
        ) : applicationActions.error ? (
          <BrutalCard className="mt-5 border-coral/35">
            <p className="text-sm text-coral">
              {errorSummary(applicationActions.error)}
            </p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => void applicationActions.mutate()}
            >
              Retry applications
            </Button>
          </BrutalCard>
        ) : applicationCount === 0 ? (
          <BrutalCard className="mt-5 flex flex-col justify-between gap-5 sm:flex-row sm:items-center">
            <div className="flex items-center gap-4">
              <div className="grid size-11 shrink-0 place-items-center rounded-lg bg-purple/10 text-purple">
                <BriefcaseBusiness className="size-5" />
              </div>
              <div>
                <p className="font-medium">No applications in progress yet.</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Open a ranked job and start tracking it when you are ready.
                </p>
              </div>
            </div>
            <Link
              href="/jobs"
              className="flex min-h-10 shrink-0 items-center gap-2 text-sm font-medium hover:text-acid"
            >
              Browse jobs <ArrowUpRight className="size-4" />
            </Link>
          </BrutalCard>
        ) : (
          <div className="mt-5 grid gap-4">
            <div className="min-w-0">
              <ApplicationPipeline
                counts={applicationActions.data?.statusCounts ?? {}}
              />
            </div>
            <div className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-border bg-border">
              {[
                ["Tracked", applicationCount, "text-acid"],
                [
                  "Due today",
                  applicationActions.data?.dueTodayCount ?? 0,
                  "text-foreground",
                ],
                [
                  "Overdue",
                  applicationActions.data?.overdueCount ?? 0,
                  "text-coral",
                ],
              ].map(([label, count, color]) => (
                <div key={String(label)} className="bg-card p-4">
                  <p className="ops-label text-muted-foreground">{label}</p>
                  <p className={`mt-2 text-3xl font-semibold ${color}`}>
                    {count}
                  </p>
                </div>
              ))}
            </div>
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              {applicationActions.data?.nearestActions.length ? (
                applicationActions.data.nearestActions.map((action) => (
                  <div
                    key={action.jobId}
                    className="grid gap-3 border-b border-border border-l-2 border-l-purple p-4 last:border-b-0 hover:bg-raised/50 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center"
                  >
                    <Link
                      href={`/jobs/${action.jobId}`}
                      className="group min-w-0"
                    >
                      <p className="flex items-center gap-2 font-medium group-hover:text-acid">
                        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-purple/10 text-purple">
                          <BriefcaseBusiness className="size-3.5" />
                        </span>
                        <span className="truncate">{action.nextAction}</span>
                      </p>
                      <p className="mt-1 truncate pl-9 text-xs text-muted-foreground">
                        {action.roleTitle} at {action.companyName}
                      </p>
                    </Link>
                    <div className="text-left sm:text-right">
                      <p className="ops-label text-purple">
                        {readableStatus(action.applicationStatus)}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {new Date(action.nextActionDueAt).toLocaleString()}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      className="cursor-pointer hover:border-acid hover:text-acid"
                      disabled={Boolean(completingActionId)}
                      onClick={() => void completeApplicationAction(action)}
                    >
                      <CheckCircle2 className="size-4" />
                      {completingActionId === action.jobId
                        ? "Saving..."
                        : "Complete"}
                    </Button>
                  </div>
                ))
              ) : (
                <p className="p-6 text-sm text-muted-foreground">
                  Your applications are tracked. Add a next action from a job
                  page to see it here.
                </p>
              )}
            </div>
          </div>
        )}
      </section>

      <details className="border-t border-border pt-4">
        <summary className="w-fit cursor-pointer text-sm font-medium">
          Shared rankings
        </summary>
        <div className="mt-4">
          <SectionHeading
            eyebrow="Preference leaderboard"
            title={leaderboardTitle}
            action={
              <div className="flex rounded-lg border border-border bg-card p-1">
                {(["daily", "weekly", "overall"] as Period[]).map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={`min-h-9 cursor-pointer rounded-md px-3 text-xs capitalize transition ${period === value ? "bg-raised text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                    onClick={() => setPeriod(value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            }
          />
          {feed.isLoading ? (
            <Skeleton className="mt-5 h-80 rounded-xl bg-raised" />
          ) : feed.data?.leaderboard.length ? (
            <div className="mt-5 overflow-hidden rounded-xl border border-border bg-card">
              {feed.data.leaderboard.map((job, index) => {
                const score = job.jediPreferenceScore ?? job.rankingScore;
                return (
                  <Link
                    key={job.id}
                    href={`/jobs/${job.id}`}
                    className="group grid gap-3 border-b border-border p-4 transition last:border-0 hover:bg-raised/60 sm:grid-cols-[3rem_minmax(0,1fr)_auto_auto] sm:items-center"
                  >
                    <span
                      className={`font-mono text-lg font-bold ${index < 3 ? "text-acid" : "text-muted-foreground"}`}
                    >
                      #{index + 1}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-purple">
                        {job.companyName}
                      </p>
                      <p className="mt-1 truncate font-medium transition group-hover:text-acid">
                        {job.roleTitle}
                      </p>
                    </div>
                    <div className="text-left sm:text-right">
                      <p className="font-mono text-base font-bold">
                        {score?.toFixed(1) ?? "--"}
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        PREFERENCE
                      </p>
                    </div>
                    <div className="min-w-24 text-left sm:text-right">
                      <p
                        className={
                          job.applyRecommendation
                            ? "text-sm font-bold text-acid"
                            : "text-sm font-bold text-coral"
                        }
                      >
                        {job.applyPreferenceProbability === null
                          ? "--"
                          : `${(job.applyPreferenceProbability * 100).toFixed(1)}%`}
                      </p>
                      <p className="text-[10px] text-muted-foreground">
                        APPLY SIGNAL
                      </p>
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : (
            <BrutalCard className="mt-5 flex items-center gap-4">
              <Trophy className="size-5 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                No ranked jobs in this period yet.
              </p>
            </BrutalCard>
          )}
        </div>
      </details>

      {session.data?.isGroupOwner && (
        <>
          <section>
            <SectionHeading
              eyebrow="Recent intake"
              title="Batches that need attention"
              action={
                <Link
                  href="/batches"
                  className="flex min-h-11 items-center gap-2 text-xs text-muted-foreground hover:text-foreground"
                >
                  View all <ArrowUpRight className="size-4" />
                </Link>
              }
            />
            {batches.isLoading ? (
              <div className="mt-5 space-y-3">
                {[0, 1, 2].map((item) => (
                  <Skeleton
                    key={item}
                    className="h-20 rounded-xl border border-border bg-raised"
                  />
                ))}
              </div>
            ) : batches.error ? (
              <BrutalCard className="mt-5 border-coral/35">
                <p className="text-sm text-coral">
                  {errorSummary(batches.error)}
                </p>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => void batches.mutate()}
                >
                  Retry batches
                </Button>
              </BrutalCard>
            ) : batches.data?.items.length ? (
              <div className="mt-4 divide-y divide-border overflow-hidden rounded-xl border border-border">
                {batches.data.items.map((batch) => (
                  <Link
                    key={batch.id}
                    href={`/batches/${batch.id}`}
                    className="grid min-h-20 gap-3 bg-card p-4 transition-colors hover:bg-raised sm:grid-cols-[1fr_auto_auto] sm:items-center"
                  >
                    <div>
                      <p className="font-medium">
                        {batch.displayName ?? "Unnamed batch"}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {new Date(batch.createdAt).toLocaleString()}
                      </p>
                    </div>
                    <span className="ops-label text-purple">
                      {readableStatus(batch.status)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {batch.jobCount} jobs
                    </span>
                  </Link>
                ))}
              </div>
            ) : (
              <BrutalCard className="mt-5 flex items-center gap-4 py-5">
                <Boxes className="size-5 text-acid" />
                <div>
                  <p className="font-medium">All caught up.</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    No batches currently need ranking attention.
                  </p>
                </div>
              </BrutalCard>
            )}
          </section>

          <section>
            <SectionHeading eyebrow="Operations" title="Workspace status" />
            <div className="mt-5 grid gap-4 xl:grid-cols-[1.1fr_.9fr]">
              <BrutalCard className="flex flex-col justify-between gap-6 p-6 sm:flex-row sm:items-center">
                <div>
                  <p className="ops-label text-muted-foreground">
                    Awaiting ranking
                  </p>
                  <p className="mt-3 text-4xl font-semibold tracking-tight">
                    {batches.data?.total ?? "--"}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    batches in the workspace queue
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Link
                    href="/batches?import=1"
                    className="flex min-h-11 items-center gap-2 rounded-lg bg-foreground px-4 text-sm font-medium text-background hover:bg-acid"
                  >
                    Import batch <ArrowUpRight className="size-4" />
                  </Link>
                  <Link
                    href="/batches"
                    className="flex min-h-11 items-center rounded-lg border border-border px-4 text-sm font-medium hover:bg-raised"
                  >
                    Review workspace
                  </Link>
                </div>
              </BrutalCard>
              <div className="space-y-3">
                <HealthLine
                  label="FastAPI process"
                  icon={Server}
                  result={live.data}
                  error={live.error}
                />
                <HealthLine
                  label="Database and migrations"
                  icon={DatabaseZap}
                  result={ready.data}
                  error={ready.error}
                />
                <Button
                  variant="ghost"
                  className="min-h-11 w-full justify-start text-muted-foreground"
                  disabled={live.isValidating || ready.isValidating}
                  onClick={() =>
                    void Promise.all([live.mutate(), ready.mutate()])
                  }
                >
                  <RefreshCw
                    className={`size-4 ${live.isValidating || ready.isValidating ? "animate-spin" : ""}`}
                  />
                  Refresh service status
                </Button>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
