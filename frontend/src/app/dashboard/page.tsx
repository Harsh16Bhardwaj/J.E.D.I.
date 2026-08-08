"use client";

import { useState } from "react";
import Link from "next/link";
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
import {
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
} from "recharts";
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
      <span className={`size-2 rounded-full ${result ? "bg-acid" : "bg-coral"}`} />
    </div>
  );
}

function SectionHeading({
  eyebrow,
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
        <p className="ops-label text-muted-foreground">{eyebrow}</p>
        <h2 className="mt-2 text-2xl font-semibold sm:text-3xl">{title}</h2>
        {description ? (
          <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

function PreferenceGauge({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <div className="grid size-20 shrink-0 place-items-center rounded-full border-4 border-muted text-muted-foreground">
        <span className="font-mono text-sm">--</span>
      </div>
    );
  }
  const value = Math.max(0, Math.min(100, score));
  return (
    <div
      className="relative size-20 shrink-0"
      aria-label={`Preference score ${value.toFixed(1)} out of 100`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          data={[{ value }]}
          innerRadius="81%"
          outerRadius="94%"
          startAngle={90}
          endAngle={-270}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar
            dataKey="value"
            fill="var(--primary)"
            background={{ fill: "var(--muted)" }}
            cornerRadius={10}
            isAnimationActive={false}
          />
        </RadialBarChart>
      </ResponsiveContainer>
      <strong className="pointer-events-none absolute inset-0 grid place-items-center text-base">
        {value.toFixed(1)}
      </strong>
    </div>
  );
}

function readableStatus(value: string) {
  return value.toLowerCase().replaceAll("_", " ");
}

function JobCard({ job }: { job: DashboardJob }) {
  const score = job.jediPreferenceScore ?? job.rankingScore;
  const probability = job.applyPreferenceProbability;
  const applySignal =
    job.applyRecommendation === true
      ? "Apply"
      : probability === null
        ? "Not ranked"
        : "Review";

  return (
    <Link
      href={`/jobs/${job.id}`}
      aria-label={`Open ${job.roleTitle} at ${job.companyName}`}
      className="group flex min-h-[22rem] min-w-0 flex-col rounded-xl border border-border bg-card p-5 transition hover:-translate-y-1 hover:border-acid/55 hover:shadow-[6px_6px_0_var(--foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-acid"
    >
      <div className="flex items-start gap-4">
        <div className="grid size-12 shrink-0 place-items-center rounded-lg border-2 border-purple/30 bg-purple/10 text-xl font-black text-purple">
          {job.companyName.trim().charAt(0).toUpperCase() || "J"}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-purple">{job.companyName}</p>
          <h3 className="mt-1 line-clamp-2 text-lg font-black uppercase leading-tight transition group-hover:text-acid">
            {job.roleTitle}
          </h3>
        </div>
        <PreferenceGauge score={score} />
      </div>

      <div className="mt-4 grid grid-cols-[1fr_auto] items-center gap-3 rounded-lg bg-raised px-3 py-2.5">
        <div className="min-w-0">
          <p className="ops-label text-muted-foreground">Salary</p>
          <p className={`mt-1 truncate text-sm font-bold ${job.salaryMin === null && job.salaryMax === null ? "text-muted-foreground" : "text-acid"}`}>
            {formatCompensationLpa(job)}
          </p>
        </div>
        <div className="text-right">
          <p className={`text-xs font-bold ${job.applyRecommendation ? "text-acid" : probability === null ? "text-muted-foreground" : "text-coral"}`}>
            {applySignal}
          </p>
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            {probability === null ? "No probability" : `${(probability * 100).toFixed(1)}% apply`}
          </p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {[job.employmentType, job.seniority, job.workMode].filter(Boolean).map((value) => (
          <span key={value} className="rounded-full border border-border px-2 py-1 text-[10px] font-bold uppercase text-muted-foreground">
            {value}
          </span>
        ))}
      </div>
      <p className="mt-4 line-clamp-3 text-sm leading-6 text-muted-foreground">
        {job.description || "No description was supplied for this job."}
      </p>
      <div className="mt-auto flex items-end justify-between gap-4 border-t border-border pt-4">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium">{job.location || "Location unspecified"}</p>
          <p className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            {postedDaysAgo(job.batchCreatedAt)} · {readableStatus(job.applicationStatus)}
          </p>
        </div>
        <span className="flex shrink-0 items-center gap-1 text-xs font-semibold transition group-hover:text-acid">
          Open job <ArrowUpRight className="size-4" />
        </span>
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
  const live = useSWR<TimedResult<Health>>("/health/live", timedGet, {
    refreshInterval: 30_000,
  });
  const ready = useSWR<TimedResult<Health>>("/health/ready", timedGet, {
    refreshInterval: 30_000,
  });
  const batches = useSWR<BatchPage>("/api/batches?page=1&pageSize=5", {
    refreshInterval: 10_000,
    revalidateOnFocus: true,
  });
  const applicationActions = useSWR<ApplicationSummary>("/api/applications/summary");
  const query = new URLSearchParams({ leaderboardPeriod: period });
  if (fresh) query.set("fresh", "true");
  const feed = useSWR<DashboardFeed>(`/api/dashboard?${query}`, {
    refreshInterval: 10_000,
    revalidateOnFocus: true,
  });

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const userName = session.data?.email.split("@")[0] ?? "there";
  const applicationCount = Object.values(applicationActions.data?.statusCounts ?? {}).reduce(
    (total, count) => total + count,
    0,
  );
  const leaderboardTitle =
    period === "daily" ? "Today's top 10" : period === "weekly" ? "This week's top 10" : "All-time top 10";

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
    <div className="space-y-12">
      <header className="border-b border-border pb-6">
        <h1 className="text-4xl font-semibold leading-none tracking-[-0.05em] sm:text-5xl">
          <span suppressHydrationWarning>{greeting}</span>, {userName}
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Your strongest jobs and next application steps, in one place.
        </p>
      </header>

      <section>
        <SectionHeading
          eyebrow="New opportunities"
          title={feed.data?.jobFeedScope === "latest" ? "Latest jobs" : "Today's jobs"}
          description={feed.data?.jobFeedScope === "latest"
            ? "No jobs were generated today, so this shows the latest available jobs ordered by JEDI preference when ranked."
            : "Today's jobs ordered by JEDI preference when ranked; apply probability remains a review signal."}
          action={
            <div className="flex flex-wrap gap-2">
              <Button
                aria-pressed={fresh}
                variant={fresh ? "secondary" : "outline"}
                className={fresh ? "border border-acid bg-acid text-background shadow-[3px_3px_0_var(--foreground)]" : "cursor-pointer hover:border-acid/50"}
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
              Showing <strong>{feed.data?.todayJobs.length ?? "..."}</strong> unseen jobs.
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
          <div className="mt-5 grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
            {[0, 1, 2, 3, 4, 5].map((item) => (
              <Skeleton key={item} className="h-[22rem] rounded-xl bg-raised" />
            ))}
          </div>
        ) : feed.error ? (
          <BrutalCard className="mt-5 border-coral/35">
            <p className="text-sm text-coral">{errorSummary(feed.error)}</p>
            <Button variant="outline" className="mt-4" onClick={() => void feed.mutate()}>
              Retry jobs
            </Button>
          </BrutalCard>
        ) : feed.data?.todayJobs.length ? (
          <>
            <div className="mt-5 grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
              {feed.data.todayJobs.slice(0, 6).map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
            </div>
            <div className="mt-5 flex justify-end">
              <Link href="/jobs" className="flex min-h-11 items-center gap-2 text-sm font-medium text-muted-foreground hover:text-acid">
                View all jobs <ArrowUpRight className="size-4" />
              </Link>
            </div>
          </>
        ) : (
          <BrutalCard className="mt-5 flex items-center justify-between gap-4">
            <div>
              <p className="font-medium">{fresh ? "All available jobs have been viewed." : "No jobs are available yet."}</p>
              <p className="mt-1 text-sm text-muted-foreground">{fresh ? "Clear the unseen filter to see them again." : "Import a recent batch to start ranking opportunities."}</p>
            </div>
            {fresh ? (
              <Button variant="ghost" className="shrink-0" onClick={() => setFresh(false)}>Clear filter</Button>
            ) : (
              <Link href="/batches?import=1" className="shrink-0 text-sm font-medium hover:text-acid">Import batch</Link>
            )}
          </BrutalCard>
        )}
      </section>

      <section>
        <SectionHeading
          eyebrow="Private follow-through"
          title="Your applications"
          action={
            <Link href="/applications" className="flex min-h-11 items-center gap-2 text-xs text-muted-foreground hover:text-foreground">
              Open pipeline <ArrowUpRight className="size-4" />
            </Link>
          }
        />
        {applicationActions.isLoading ? (
          <Skeleton className="mt-5 h-36 rounded-xl bg-raised" />
        ) : applicationActions.error ? (
          <BrutalCard className="mt-5 border-coral/35">
            <p className="text-sm text-coral">{errorSummary(applicationActions.error)}</p>
            <Button variant="outline" className="mt-4" onClick={() => void applicationActions.mutate()}>
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
                <p className="mt-1 text-sm text-muted-foreground">Open a ranked job and start tracking it when you are ready.</p>
              </div>
            </div>
            <Link href="/jobs" className="flex min-h-10 shrink-0 items-center gap-2 text-sm font-medium hover:text-acid">
              Browse jobs <ArrowUpRight className="size-4" />
            </Link>
          </BrutalCard>
        ) : (
          <div className="mt-5 grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
            <div className="grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-border bg-border lg:grid-cols-1">
              {[
                ["Active", applicationCount, "text-acid"],
                ["Due today", applicationActions.data?.dueTodayCount ?? 0, "text-foreground"],
                ["Overdue", applicationActions.data?.overdueCount ?? 0, "text-coral"],
              ].map(([label, count, color]) => (
                <div key={String(label)} className="bg-card p-4">
                  <p className="ops-label text-muted-foreground">{label}</p>
                  <p className={`mt-2 text-3xl font-semibold ${color}`}>{count}</p>
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
                    <Link href={`/jobs/${action.jobId}`} className="group min-w-0">
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
                      <p className="ops-label text-purple">{readableStatus(action.applicationStatus)}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{new Date(action.nextActionDueAt).toLocaleString()}</p>
                    </div>
                    <Button
                      variant="outline"
                      className="cursor-pointer hover:border-acid hover:text-acid"
                      disabled={Boolean(completingActionId)}
                      onClick={() => void completeApplicationAction(action)}
                    >
                      <CheckCircle2 className="size-4" />
                      {completingActionId === action.jobId ? "Saving..." : "Complete"}
                    </Button>
                  </div>
                ))
              ) : (
                <p className="p-6 text-sm text-muted-foreground">Your applications are tracked. Add a next action from a job page to see it here.</p>
              )}
            </div>
          </div>
        )}
      </section>

      <section>
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
                  <span className={`font-mono text-lg font-bold ${index < 3 ? "text-acid" : "text-muted-foreground"}`}>
                    #{index + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-purple">{job.companyName}</p>
                    <p className="mt-1 truncate font-medium transition group-hover:text-acid">{job.roleTitle}</p>
                  </div>
                  <div className="text-left sm:text-right">
                    <p className="font-mono text-base font-bold">{score?.toFixed(1) ?? "--"}</p>
                    <p className="text-[10px] text-muted-foreground">PREFERENCE</p>
                  </div>
                  <div className="min-w-24 text-left sm:text-right">
                    <p className={job.applyRecommendation ? "text-sm font-bold text-acid" : "text-sm font-bold text-coral"}>
                      {job.applyPreferenceProbability === null ? "--" : `${(job.applyPreferenceProbability * 100).toFixed(1)}%`}
                    </p>
                    <p className="text-[10px] text-muted-foreground">APPLY SIGNAL</p>
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <BrutalCard className="mt-5 flex items-center gap-4">
            <Trophy className="size-5 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">No ranked jobs in this period yet.</p>
          </BrutalCard>
        )}
      </section>

      <section>
        <SectionHeading
          eyebrow="Recent intake"
          title="Batches that need attention"
          action={
            <Link href="/batches" className="flex min-h-11 items-center gap-2 text-xs text-muted-foreground hover:text-foreground">
              View all <ArrowUpRight className="size-4" />
            </Link>
          }
        />
        {batches.isLoading ? (
          <div className="mt-5 space-y-3">
            {[0, 1, 2].map((item) => <Skeleton key={item} className="h-20 rounded-xl border border-border bg-raised" />)}
          </div>
        ) : batches.error ? (
          <BrutalCard className="mt-5 border-coral/35">
            <p className="text-sm text-coral">{errorSummary(batches.error)}</p>
            <Button variant="outline" className="mt-4" onClick={() => void batches.mutate()}>Retry batches</Button>
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
                  <p className="font-medium">{batch.displayName ?? "Unnamed batch"}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{new Date(batch.createdAt).toLocaleString()}</p>
                </div>
                <span className="ops-label text-purple">{readableStatus(batch.status)}</span>
                <span className="text-xs text-muted-foreground">{batch.jobCount} jobs</span>
              </Link>
            ))}
          </div>
        ) : (
          <BrutalCard className="mt-5 flex items-center gap-4 py-5">
            <Boxes className="size-5 text-acid" />
            <div>
              <p className="font-medium">All caught up.</p>
              <p className="mt-1 text-sm text-muted-foreground">No batches currently need ranking attention.</p>
            </div>
          </BrutalCard>
        )}
      </section>

      <section>
        <SectionHeading eyebrow="Operations" title="Workspace status" />
        <div className="mt-5 grid gap-4 xl:grid-cols-[1.1fr_.9fr]">
          <BrutalCard className="flex flex-col justify-between gap-6 p-6 sm:flex-row sm:items-center">
            <div>
              <p className="ops-label text-muted-foreground">Awaiting ranking</p>
              <p className="mt-3 text-4xl font-semibold tracking-tight">{batches.data?.total ?? "--"}</p>
              <p className="mt-1 text-sm text-muted-foreground">batches in the workspace queue</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Link href="/batches?import=1" className="flex min-h-11 items-center gap-2 rounded-lg bg-foreground px-4 text-sm font-medium text-background hover:bg-acid">
                Import batch <ArrowUpRight className="size-4" />
              </Link>
              <Link href="/batches" className="flex min-h-11 items-center rounded-lg border border-border px-4 text-sm font-medium hover:bg-raised">
                Review workspace
              </Link>
            </div>
          </BrutalCard>
          <div className="space-y-3">
            <HealthLine label="FastAPI process" icon={Server} result={live.data} error={live.error} />
            <HealthLine label="Database and migrations" icon={DatabaseZap} result={ready.data} error={ready.error} />
            <Button
              variant="ghost"
              className="min-h-11 w-full justify-start text-muted-foreground"
              disabled={live.isValidating || ready.isValidating}
              onClick={() => void Promise.all([live.mutate(), ready.mutate()])}
            >
              <RefreshCw className={`size-4 ${live.isValidating || ready.isValidating ? "animate-spin" : ""}`} />
              Refresh service status
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
