"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowDownWideNarrow,
  ArrowLeft,
  ArrowUpRight,
  BarChart3,
  ChartNoAxesCombined,
  Check,
  LoaderCircle,
  NotebookPen,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { StatusBadge } from "@/components/status-badge";
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
  type BatchDetail,
  type BatchMetrics,
  type ProcessingRun,
  type RankingExecutionResult,
  type RankingQueueResult,
  type RankingResult,
  type RankingRetryResult,
  type User,
} from "@/lib/api";
import { formatCompensationLpa, postedDaysAgo } from "@/lib/job-display";
import { cn } from "@/lib/utils";

type ActionKind = "normalize" | "rank" | "delete";
type ActiveOperation = {
  kind: "normalize" | "rank";
  estimatedSeconds: number;
};
type RankingSort = "preference" | "probability";

const actionCopy: Record<
  ActionKind,
  { title: string; description: string; confirm: string }
> = {
  normalize: {
    title: "Normalize this batch?",
    description:
      "JEDI will generate versioned, model-ready features using the active profile. Stored source jobs remain unchanged.",
    confirm: "Normalize batch",
  },
  rank: {
    title: "Send for evaluation?",
    description:
      "JEDI will create a durable run, load the embedded model, score every prepared job, and save the complete ranking atomically.",
    confirm: "Rank this batch",
  },
  delete: {
    title: "Permanently delete this batch?",
    description:
      "This cannot be undone. The backend will refuse deletion if annotations, training examples or rankings already exist.",
    confirm: "Delete permanently",
  },
};

const componentLabels: Record<string, string> = {
  role_title_preference_score: "Title fit",
  role_family_preference_score: "Role-family fit",
  seniority_profile_fit_score: "Seniority fit",
  location_profile_fit_score: "Location fit",
  work_mode_fit_score: "Work-mode fit",
  experience_profile_fit_score: "Experience fit",
  skills_profile_fit_score: "Skills fit",
  salary_profile_fit_score: "Salary fit",
  overall_preference_score: "Overall fit",
};

function componentMaximum(name: string) {
  return name === "salary_profile_fit_score" ? 8 : 5;
}

function durationLabel(run: ProcessingRun) {
  const modelTotal = run.invocation?.timingsMs?.total;
  if (typeof modelTotal === "number" && Number.isFinite(modelTotal)) {
    return modelTotal < 1_000
      ? `${Math.round(modelTotal)} ms`
      : `${(modelTotal / 1_000).toFixed(1)} s`;
  }
  if (run.startedAt && run.completedAt) {
    const elapsed = new Date(run.completedAt).getTime() - new Date(run.startedAt).getTime();
    if (Number.isFinite(elapsed) && elapsed >= 0) {
      return elapsed < 1_000 ? `${elapsed} ms` : `${(elapsed / 1_000).toFixed(1)} s`;
    }
  }
  return "Timing pending";
}

function rankingCardClass(index: number) {
  if (index === 0) return "border-acid";
  if (index === 1) return "border-purple";
  if (index === 2) return "border-coral";
  if (index < 15) return "border-purple/35 hover:border-purple/70";
  return "border-border hover:border-acid/50";
}

function rankClass(index: number) {
  if (index === 0) return "text-acid";
  if (index === 1) return "text-purple";
  if (index === 2) return "text-coral";
  return index < 15 ? "text-purple" : "text-muted-foreground";
}

function rankingGlow(index: number) {
  if (index === 0) return { boxShadow: "0 0 0 1px #a8c67a80, 0 0 30px #a8c67a45" };
  if (index === 1) return { boxShadow: "0 0 0 1px #8f84b680, 0 0 26px #8f84b640" };
  if (index === 2) return { boxShadow: "0 0 0 1px #c76f6280, 0 0 24px #c76f623b" };
  return undefined;
}

function PreferenceGauge({ score }: { score: number }) {
  const value = Math.max(0, Math.min(100, score));
  return (
    <div className="relative size-24 shrink-0" aria-label={`Preference score ${value.toFixed(1)} out of 100`}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          data={[{ value }]}
          innerRadius="80%"
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
      <div className="pointer-events-none absolute inset-0 grid place-content-center text-center">
        <strong className="text-xl leading-none">{value.toFixed(1)}</strong>
      </div>
    </div>
  );
}

function ProbabilityBar({ probability, threshold = 0.6 }: { probability: number; threshold?: number }) {
  const percentage = Math.max(0, Math.min(100, probability * 100));
  const thresholdPercentage = Math.max(0, Math.min(100, threshold * 100));
  const passes = percentage >= thresholdPercentage;
  return (
    <div className="min-w-0">
      <div className="flex items-end justify-between gap-3">
        <span className="ops-label text-muted-foreground">Apply probability</span>
        <strong className={passes ? "text-acid" : "text-coral"}>{percentage.toFixed(1)}%</strong>
      </div>
      <div className="relative mt-2 h-2.5 overflow-visible rounded-full bg-muted">
        <div
          className={`h-full rounded-full ${passes ? "bg-acid" : "bg-coral"}`}
          style={{ width: `${percentage}%` }}
        />
        <span className="absolute -top-1 h-4 w-px bg-foreground" style={{ left: `${thresholdPercentage}%` }} aria-hidden="true" />
      </div>
      <div className="mt-1 flex justify-between text-[9px] uppercase text-muted-foreground">
        <span>0%</span><span>{thresholdPercentage.toFixed(0)}% threshold</span><span>100%</span>
      </div>
    </div>
  );
}

function FitBreakdown({ scores }: { scores: Record<string, number> }) {
  return (
    <details className="border-t border-border pt-3 md:col-span-5">
      <summary className="ops-label cursor-pointer text-muted-foreground hover:text-acid">Fit breakdown</summary>
      <div className="mt-3 grid gap-x-5 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
        {Object.entries(scores).map(([name, value]) => {
          const maximum = componentMaximum(name);
          const percentage = Math.max(0, Math.min(100, (value / maximum) * 100));
          return (
            <div key={name}>
              <div className="flex justify-between gap-3 text-[11px]">
                <span>{componentLabels[name] ?? name.replaceAll("_", " ")}</span>
                <strong>{value.toFixed(1)} / {maximum}</strong>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-purple" style={{ width: `${percentage}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </details>
  );
}

function subscribeLocation(callback: () => void) {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
}

function ErrorPanel({ error }: { error: unknown }) {
  return (
    <div role="alert" className="border-2 border-coral bg-coral/10 p-4">
      <p className="font-bold text-coral">{errorSummary(error)}</p>
      {isApiError(error) && error.requestId && (
        <details className="mt-3">
          <summary className="ops-label cursor-pointer text-muted-foreground">
            Technical details
          </summary>
          <p className="mt-2 font-mono text-xs">Request ID: {error.requestId}</p>
        </details>
      )}
    </div>
  );
}

function BatchMetricsPanel({
  data,
  loading,
  error,
  retry,
}: {
  data?: BatchMetrics;
  loading: boolean;
  error: unknown;
  retry: () => void;
}) {
  if (loading) return <Skeleton className="h-[34rem] border-2 border-foreground" />;
  if (error) {
    return <div className="space-y-4"><ErrorPanel error={error} /><Button variant="outline" onClick={retry}>Retry metrics</Button></div>;
  }
  if (!data) return null;

  const recommendationData = [
    { label: "Recommended", count: data.recommendedCount, color: "#a8c67a" },
    { label: "Below threshold", count: Math.max(0, data.rankedCount - data.recommendedCount), color: "#c76f62" },
  ];
  const engagementData = [
    { label: "Viewed", count: data.viewedCount, color: "#6f8fa3" },
    { label: "Bookmarked", count: data.bookmarkedCount, color: "#8f84b6" },
    { label: "Applied", count: data.appliedCount, color: "#a8c67a" },
  ];
  const components = Object.entries(data.componentAverages)
    .map(([name, value]) => ({ label: componentLabels[name] ?? name.replaceAll("_", " "), value }))
    .sort((left, right) => right.value - left.value);
  const tooltipStyle = { background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8 };

  return (
    <section className="space-y-6">
      <div>
        <p className="ops-label text-acid">Batch intelligence</p>
        <h2 className="mt-2 text-3xl font-black uppercase">Metrics</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Latest successful model run plus your private viewing, bookmark, and application activity.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Average score", data.averageScore?.toFixed(1) ?? "—", `${data.rankedCount}/${data.jobCount} ranked`],
          ["Top 25 average", data.top25AverageScore?.toFixed(1) ?? "—", "Strongest persisted ranks"],
          ["Application rate", `${(data.applicationRate * 100).toFixed(1)}%`, `${data.appliedCount} jobs applied`],
          ["Recommended", data.recommendedCount, `${((data.averageApplyProbability ?? 0) * 100).toFixed(1)}% avg apply probability`],
        ].map(([label, value, detail]) => (
          <BrutalCard key={String(label)} className="bg-raised p-4">
            <p className="ops-label text-muted-foreground">{label}</p>
            <p className="mt-2 text-3xl font-black">{value}</p>
            <p className="mt-2 text-xs text-muted-foreground">{detail}</p>
          </BrutalCard>
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <BrutalCard>
          <h3 className="text-lg font-black uppercase">Score distribution</h3>
          <p className="mt-1 text-xs text-muted-foreground">Preference scores from the latest successful ranking.</p>
          <div className="mt-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.scoreBuckets}>
                <CartesianGrid vertical={false} stroke="var(--border)" />
                <XAxis dataKey="label" tickLine={false} axisLine={false} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--muted)" }} />
                <Bar dataKey="count" fill="#8f84b6" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </BrutalCard>
        <BrutalCard>
          <h3 className="text-lg font-black uppercase">Model recommendation</h3>
          <p className="mt-1 text-xs text-muted-foreground">XGBoost apply gate for all ranked jobs.</p>
          <div className="mt-4 grid min-h-64 items-center sm:grid-cols-[minmax(0,1fr)_12rem]">
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={recommendationData} dataKey="count" nameKey="label" innerRadius={58} outerRadius={92} paddingAngle={3}>
                  {recommendationData.map((item) => <Cell key={item.label} fill={item.color} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-3">
              {recommendationData.map((item) => (
                <div key={item.label} className="flex items-center justify-between gap-3 text-sm">
                  <span className="flex items-center gap-2"><span className="size-2 rounded-full" style={{ background: item.color }} />{item.label}</span>
                  <strong>{item.count}</strong>
                </div>
              ))}
            </div>
          </div>
        </BrutalCard>
        <BrutalCard>
          <h3 className="text-lg font-black uppercase">Your activity</h3>
          <p className="mt-1 text-xs text-muted-foreground">Private to your group membership, never shared across members.</p>
          <div className="mt-4 h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={engagementData} layout="vertical" margin={{ left: 18 }}>
                <CartesianGrid horizontal={false} stroke="var(--border)" />
                <XAxis type="number" allowDecimals={false} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="label" width={84} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--muted)" }} />
                <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                  {engagementData.map((item) => <Cell key={item.label} fill={item.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </BrutalCard>
        <BrutalCard>
          <h3 className="text-lg font-black uppercase">Average fit dimensions</h3>
          <p className="mt-1 text-xs text-muted-foreground">Ridge predictions behind the preference score.</p>
          {components.length ? (
            <div className="mt-4 h-60">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={components} layout="vertical" margin={{ left: 28 }}>
                  <CartesianGrid horizontal={false} stroke="var(--border)" />
                  <XAxis type="number" domain={[0, 8]} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="label" width={110} axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
                  <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--muted)" }} />
                  <Bar dataKey="value" fill="#6f8fa3" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : <p className="mt-8 text-sm text-muted-foreground">Component predictions are not available for this ranking.</p>}
        </BrutalCard>
      </div>
    </section>
  );
}

export default function BatchDetailPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const router = useRouter();
  const { mutate: mutateGlobal } = useSWRConfig();
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [action, setAction] = useState<ActionKind>();
  const [actionError, setActionError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [activeOperation, setActiveOperation] = useState<ActiveOperation>();
  const [operationElapsed, setOperationElapsed] = useState(0);
  const locationSearch = useSyncExternalStore(
    subscribeLocation,
    () => window.location.search,
    () => "",
  );
  const locationParams = new URLSearchParams(locationSearch);
  const requestedTab = locationParams.get("tab");
  const [tabOverride, setTab] = useState<"jobs" | "rankings" | "metrics">();
  const tab = tabOverride ?? (requestedTab === "rankings" || requestedTab === "metrics" ? requestedTab : "jobs");
  const [selectedRunOverride, setSelectedRunId] = useState<string>();
  const selectedRunId = selectedRunOverride ?? locationParams.get("runId") ?? undefined;
  const [executionError, setExecutionError] = useState<unknown>();
  const [rankingSort, setRankingSort] = useState<RankingSort>("preference");
  const endpoint = `/api/batches/${batchId}${search ? `?search=${encodeURIComponent(search)}` : ""}`;
  const detail = useSWR<BatchDetail>(endpoint);
  const session = useSWR<User>("/api/auth/me");
  const runs = useSWR<ProcessingRun[]>(
    `/api/batches/${batchId}/processing-runs`,
    { refreshInterval: (data) => data?.some((run) => ["QUEUED", "RUNNING"].includes(run.effectiveStatus)) ? 2000 : 0 },
  );
  const selectedRun = runs.data?.find((run) => run.id === selectedRunId);
  const successfulRunId =
    selectedRun?.status === "SUCCEEDED"
      ? selectedRun.id
      : runs.data?.find((run) => run.status === "SUCCEEDED")?.id;
  const rankings = useSWR<RankingResult[]>(
    tab === "rankings"
      ? `/api/batches/${batchId}/rankings${successfulRunId ? `?runId=${successfulRunId}` : ""}`
      : null,
  );
  const metrics = useSWR<BatchMetrics>(
    tab === "metrics" ? `/api/batches/${batchId}/metrics` : null,
  );
  const sortedRankings = rankings.data
    ? [...rankings.data].sort((left, right) => {
        if (rankingSort === "probability") {
          return right.applyPreferenceProbability - left.applyPreferenceProbability
            || (right.rankingScore ?? right.jediPreferenceScore) - (left.rankingScore ?? left.jediPreferenceScore)
            || left.rank - right.rank;
        }
        return (right.rankingScore ?? right.jediPreferenceScore) - (left.rankingScore ?? left.jediPreferenceScore)
          || right.applyPreferenceProbability - left.applyPreferenceProbability
          || left.rank - right.rank;
      })
    : [];

  useEffect(() => {
    if (!activeOperation) return;
    const timer = window.setInterval(() => setOperationElapsed((value) => value + 1), 1_000);
    return () => window.clearInterval(timer);
  }, [activeOperation]);

  function selectTab(next: "jobs" | "rankings" | "metrics", runId?: string) {
    setTab(next);
    if (runId) setSelectedRunId(runId);
    const params = new URLSearchParams(window.location.search);
    params.set("tab", next);
    if (runId) params.set("runId", runId);
    else if (next !== "rankings") params.delete("runId");
    router.replace(`/batches/${batchId}?${params.toString()}`, { scroll: false });
  }

  async function refreshProductCaches() {
    await mutateGlobal(
      (key) =>
        typeof key === "string" &&
        (key.startsWith("/api/batches") || key.startsWith("/api/dashboard")),
      undefined,
      { revalidate: true },
    );
  }

  async function runAction() {
    if (!action || busy) return;
    const requestedAction = action;
    if (requestedAction !== "delete") {
      const jobCount = detail.data?.batch.jobCount ?? 25;
      const estimatedSeconds = requestedAction === "normalize"
        ? Math.max(6, Math.ceil(jobCount / 25) * 2)
        : Math.max(10, Math.ceil(jobCount / 25) * 3);
      setActiveOperation({
        kind: requestedAction,
        estimatedSeconds,
      });
      setOperationElapsed(0);
      setAction(undefined);
    }
    setBusy(true);
    setActionError(undefined);
    try {
      if (requestedAction === "delete") {
        await apiRequest<void>(`/api/batches/${batchId}`, { method: "DELETE" });
        toast.success("Batch deleted.");
        await refreshProductCaches();
        router.replace("/batches");
        return;
      }
      if (requestedAction === "rank") {
        const queued = await apiRequest<RankingQueueResult>(
          `/api/batches/${batchId}/rank`,
          { method: "POST" },
        );
        selectTab("rankings", queued.processingRunId);
        await runs.mutate();
        const executed = await apiRequest<RankingExecutionResult>(
          `/api/processing-runs/${queued.processingRunId}/execute`,
          { method: "POST" },
        );
        toast.success(
          executed.status === "SUCCEEDED" ? "Ranking completed." : "Ranking is already running.",
          { description: executed.rankingCount ? `${executed.rankingCount} jobs ranked.` : undefined },
        );
        await Promise.all([runs.mutate(), rankings.mutate()]);
      } else {
        const response = await apiRequest<{ status: string }>(
          `/api/batches/${batchId}/normalize`,
          { method: "POST" },
        );
        toast.success("Batch normalization completed.", {
          description: `Current state: ${response.status}`,
        });
      }
      await refreshProductCaches();
      setAction(undefined);
    } catch (error) {
      setActionError(error);
      if (requestedAction === "rank") setExecutionError(error);
      toast.error(errorSummary(error), {
        description:
          isApiError(error) && error.requestId
            ? `Request ${error.requestId}`
            : undefined,
      });
    } finally {
      setBusy(false);
      setActiveOperation(undefined);
    }
  }

  async function retryRun(runId: string) {
    if (busy) return;
    setActiveOperation({ kind: "rank", estimatedSeconds: 12 });
    setOperationElapsed(0);
    setBusy(true);
    setExecutionError(undefined);
    try {
      const retry = await apiRequest<RankingRetryResult>(
        `/api/processing-runs/${runId}/retry`,
        { method: "POST" },
      );
      selectTab("rankings", retry.processingRunId);
      await runs.mutate();
      const executed = await apiRequest<RankingExecutionResult>(
        `/api/processing-runs/${retry.processingRunId}/execute`,
        { method: "POST" },
      );
      toast.success("Retry completed.", {
        description: `${executed.rankingCount} jobs ranked.`,
      });
      await Promise.all([refreshProductCaches(), runs.mutate(), rankings.mutate()]);
    } catch (error) {
      setExecutionError(error);
      toast.error(errorSummary(error));
    } finally {
      setBusy(false);
      setActiveOperation(undefined);
    }
  }

  if (detail.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-44 border-2 border-foreground bg-raised" />
        {[0, 1, 2].map((item) => (
          <Skeleton key={item} className="h-32 border-2 border-foreground bg-raised" />
        ))}
      </div>
    );
  }

  if (detail.error || !detail.data) {
    const missing = isApiError(detail.error) && detail.error.status === 404;
    return (
      <BrutalCard className="max-w-2xl border-coral">
        <p className="ops-label text-coral">{missing ? "Batch not found" : "Batch unavailable"}</p>
        <h1 className="mt-4 text-4xl font-black uppercase">
          {missing ? "This batch does not exist." : "JEDI could not load this batch."}
        </h1>
        <p className="mt-4 text-sm text-muted-foreground">{errorSummary(detail.error)}</p>
        <div className="mt-6 flex gap-3">
          <Button variant="outline" className="min-h-11 border-2" onClick={() => router.push("/batches")}>
            <ArrowLeft className="size-4" /> Batches
          </Button>
          {!missing && (
            <Button className="min-h-11" onClick={() => void detail.mutate()}>
              Retry
            </Button>
          )}
        </div>
      </BrutalCard>
    );
  }

  const { batch, actions, jobs, normalizationComplete, manualAnnotationCount } = detail.data;
  const elapsedSeconds = activeOperation ? operationElapsed : 0;
  const remainingSeconds = activeOperation
    ? Math.max(0, activeOperation.estimatedSeconds - elapsedSeconds)
    : 0;
  const operationProgress = activeOperation
    ? Math.min(95, Math.round((elapsedSeconds / activeOperation.estimatedSeconds) * 100))
    : 0;
  return (
    <div className="space-y-9">
      <div>
        <Link href="/batches" className="ops-label inline-flex min-h-11 items-center gap-2 text-muted-foreground hover:text-acid">
          <ArrowLeft className="size-4" /> Back to batches
        </Link>
        <div className="mt-4 flex flex-wrap items-end justify-between gap-6 border-b-2 border-foreground pb-7">
          <div>
            <StatusBadge tone={batch.status === "FAILED" ? "warning" : "queued"}>
              {batch.status}
            </StatusBadge>
            <h1 className="mt-4 text-4xl font-black uppercase tracking-[-0.05em] sm:text-6xl">
              {batch.displayName ?? "Imported batch"}
            </h1>
            <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
              {batch.externalBatchId}
            </p>
            <p className="mt-2 font-mono text-xs text-muted-foreground">
              batch {batch.id} · schema {batch.schemaVersion}
              {successfulRunId ? ` · model ${runs.data?.find((run) => run.id === successfulRunId)?.modelVersionId ?? "unknown"}` : ""}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {[
                ["Jobs", batch.jobCount, "text-acid"],
                ["Duplicates", batch.duplicateCount, "text-purple"],
                ["Annotations", manualAnnotationCount, "text-coral"],
              ].map(([label, value, color]) => (
                <div key={label as string} className="flex items-baseline gap-2 rounded-lg border border-border bg-raised px-3 py-2">
                  <strong className={`text-lg ${color}`}>{value}</strong>
                  <span className="ops-label text-muted-foreground">{label}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="flex flex-wrap justify-end gap-2">
              <Link
                href={`/misc/annotation/${batchId}`}
                className={cn(buttonVariants({ variant: "outline" }), "min-h-10 cursor-pointer border-2 px-3 text-xs hover:border-purple hover:bg-purple/10")}
              >
                <NotebookPen className="size-4" /> Annotate
              </Link>
              <Button
              variant="outline"
              className="min-h-10 cursor-pointer border-2 px-3 text-xs hover:border-acid hover:bg-acid/10 disabled:cursor-not-allowed disabled:opacity-45"
              disabled={busy || normalizationComplete || !actions.canNormalize}
              title={normalizationComplete ? "All jobs are prepared for the active profile and model contract." : actions.canNormalize ? undefined : "Normalization is unavailable in this state."}
              onClick={() => setAction("normalize")}
            >
              {normalizationComplete ? <Check className="size-4" /> : <Sparkles className="size-4" />}
              {normalizationComplete ? "Ready" : "Normalize"}
              </Button>
              <Button
              className="min-h-10 cursor-pointer rounded-lg border border-purple/30 bg-purple/10 px-3 text-xs text-purple hover:border-purple hover:bg-purple/20 disabled:cursor-not-allowed"
              disabled={busy || !actions.canProcessRanks}
              title={actions.canProcessRanks ? undefined : "Complete normalization before evaluation."}
              onClick={() => setAction("rank")}
            >
              <ChartNoAxesCombined className="size-4" /> Rank
              </Button>
              <Button
              variant="destructive"
              className="min-h-10 cursor-pointer border-2 border-coral px-3 text-xs text-coral hover:bg-coral/15 disabled:cursor-not-allowed"
              disabled={busy || !actions.canDelete}
              title={actions.canDelete ? undefined : "Protected batch data prevents deletion."}
              onClick={() => setAction("delete")}
            >
              <Trash2 className="size-4" /> Delete
              </Button>
            </div>
            {!actions.canDelete && (
              <p className="mt-2 max-w-xl text-right text-[11px] leading-5 text-muted-foreground">
                Delete is disabled because this batch has annotations, training data, or ranking history that must remain auditable.
              </p>
            )}
          </div>
        </div>
      </div>

      {activeOperation && (
        <BrutalCard className="border-purple bg-purple/10" aria-live="polite">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="flex items-center gap-2 font-black uppercase text-purple">
                <LoaderCircle className="size-4 animate-spin" />
                {activeOperation.kind === "normalize" ? "Normalizing batch" : "Ranking batch"}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                This is continuing in the background of this page. You can inspect jobs while it finishes.
              </p>
            </div>
            <div className="text-right font-mono text-xs">
              <p>{elapsedSeconds}s elapsed</p>
              <p className="mt-1 text-muted-foreground">
                {remainingSeconds > 0 ? `about ${remainingSeconds}s remaining` : "finishing safely..."}
              </p>
            </div>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-background" aria-hidden="true">
            <div
              className="h-full rounded-full bg-purple transition-[width] duration-500"
              style={{ width: `${Math.max(4, operationProgress)}%` }}
            />
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">
            Time is an estimate; completion is confirmed only after the database transaction succeeds.
          </p>
        </BrutalCard>
      )}

      {!action && !activeOperation && Boolean(actionError) && <ErrorPanel error={actionError} />}

      <div className="flex gap-2 border-b-2 border-foreground" role="tablist" aria-label="Batch views">
        <Button
          role="tab"
          aria-selected={tab === "jobs"}
          variant={tab === "jobs" ? "default" : "ghost"}
          className="min-h-11 rounded-b-none"
          onClick={() => selectTab("jobs")}
        >
          Jobs ({batch.jobCount})
        </Button>
        <Button
          role="tab"
          aria-selected={tab === "rankings"}
          variant={tab === "rankings" ? "default" : "ghost"}
          className="min-h-11 rounded-b-none"
          onClick={() => selectTab("rankings")}
        >
          <ChartNoAxesCombined className="size-4" /> Rankings
        </Button>
        <Button
          role="tab"
          aria-selected={tab === "metrics"}
          variant={tab === "metrics" ? "default" : "ghost"}
          className="min-h-11 rounded-b-none"
          onClick={() => selectTab("metrics")}
        >
          <BarChart3 className="size-4" /> Metrics
        </Button>
      </div>

      {tab === "jobs" ? <section>
        <div className="flex max-w-3xl gap-2 border-b-2 border-foreground pb-4">
          <div className="relative min-w-0 flex-1">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchDraft}
              onChange={(event) => setSearchDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") setSearch(searchDraft.trim());
              }}
              placeholder="Search company or title"
              className="min-h-11 border-2 bg-card pl-10"
            />
          </div>
          <Button className="min-h-11 cursor-pointer px-5 hover:bg-acid" onClick={() => setSearch(searchDraft.trim())}>
            <Search className="size-4" /> Search
          </Button>
        </div>

        {jobs.length ? (
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-busy={detail.isValidating}>
            {jobs.map((job) => (
              <BrutalCard key={job.id} className="flex min-h-[25rem] flex-col bg-card transition hover:-translate-y-1 hover:border-purple/60 hover:shadow-[6px_6px_0_var(--foreground)]">
                <div className="flex items-start gap-4">
                  <div className="grid size-12 shrink-0 place-items-center rounded-lg border-2 border-purple/30 bg-purple/10 text-xl font-black text-purple" aria-hidden="true">
                    {job.companyName.trim().charAt(0).toUpperCase() || "J"}
                  </div>
                  <div className="min-w-0">
                    <Link href={`/jobs/${job.id}`} className="block hover:text-acid">
                      <h2 className="line-clamp-2 text-xl font-black uppercase leading-tight">{job.roleTitle}</h2>
                    </Link>
                    <p className="mt-1 truncate text-sm font-semibold text-purple">{job.companyName}</p>
                  </div>
                </div>
                <p className="mt-4 rounded-md bg-raised px-3 py-2 text-xs text-muted-foreground">
                  {job.location || "Location unspecified"}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {[job.employmentType, job.seniority, job.workMode].filter(Boolean).map((value) => (
                    <span key={value} className="rounded-full border border-border px-2 py-1 text-[10px] font-bold uppercase">{value}</span>
                  ))}
                </div>
                <p className="mt-4 line-clamp-4 text-sm leading-6 text-muted-foreground">
                  {job.description}
                </p>
                <div className="mt-auto border-t border-border pt-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="ops-label text-muted-foreground">Salary</p>
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      {postedDaysAgo(batch.createdAt)}
                    </p>
                  </div>
                  <p className="mt-1 font-bold text-acid">{formatCompensationLpa(job)}</p>
                </div>
                <Link
                  href={`/jobs/${job.id}`}
                  className="ops-label mt-4 flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg bg-foreground px-4 text-background transition hover:bg-purple"
                >
                  View job <ArrowUpRight className="size-4" />
                </Link>
              </BrutalCard>
            ))}
          </div>
        ) : (
          <BrutalCard className="mt-4 bg-raised text-center">
            <p className="ops-label text-muted-foreground">No matching jobs</p>
          </BrutalCard>
        )}
      </section> : tab === "metrics" ? (
        <BatchMetricsPanel
          data={metrics.data}
          loading={metrics.isLoading}
          error={metrics.error}
          retry={() => void metrics.mutate()}
        />
      ) : (
        <section className="space-y-6">
          {Boolean(executionError) && <ErrorPanel error={executionError} />}
          <div className="grid items-start gap-5 xl:grid-cols-[18rem_minmax(0,1fr)]">
            <aside className="space-y-4 xl:sticky xl:top-24">
              <BrutalCard className="border-acid/30 bg-acid/5">
                <p className="font-bold">Preference score / 100</p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  A weighted relative-fit index used to order jobs. It is not a probability or a promise that you should apply.
                </p>
                <p className="mt-5 font-bold">Apply probability</p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  A separate conservative XGBoost decision. The current model recommends applying only at 60% or above.
                </p>
                <p className="mt-5 border-t border-acid/20 pt-4 text-xs leading-5 text-muted-foreground">
                  Component scores are Ridge model predictions of your fit dimensions, not annotations you previously entered.
                </p>
              </BrutalCard>

              <BrutalCard className="bg-raised">
                <p className="ops-label text-purple">Ranking history</p>
                <div className="mt-4 max-h-[32rem] space-y-3 overflow-y-auto pr-1">
                  {runs.isLoading && <Skeleton className="h-36 border-2" />}
                  {runs.data?.filter((run) => run.stage === "ranking").map((run) => (
                    <div
                      role="button"
                      tabIndex={0}
                      key={run.id}
                      onClick={() => selectTab("rankings", run.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") selectTab("rankings", run.id);
                      }}
                      className={`w-full cursor-pointer rounded-lg border-2 p-4 text-left transition hover:-translate-y-0.5 hover:border-purple ${(selectedRunId ?? successfulRunId) === run.id ? "border-purple bg-purple/10" : "border-border bg-card"}`}
                    >
                      <span className="flex items-center justify-between gap-3">
                        <StatusBadge tone={run.effectiveStatus === "FAILED" || run.effectiveStatus === "STALE" ? "warning" : "queued"}>
                          {run.effectiveStatus === "SUCCEEDED" ? "Completed" : run.effectiveStatus}
                        </StatusBadge>
                        <span className="font-mono text-[10px] text-muted-foreground">{durationLabel(run)}</span>
                      </span>
                      <span className="mt-4 block text-sm font-black uppercase">
                        {run.modelName ?? run.modelVersionId ?? "Model not pinned"}
                      </span>
                      <span className="mt-2 block text-xs text-muted-foreground">
                        {new Date(run.createdAt).toLocaleDateString()} at {new Date(run.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="mt-3 block rounded-md bg-background px-3 py-2 font-mono text-[10px] uppercase text-muted-foreground">
                        Attempt {run.attempt} · {run.invocation?.coldStart ? "Cold start" : "Warm start"} · {run.phase.replaceAll("_", " ")}
                      </span>
                      {run.errorMessage && <span className="mt-3 block text-xs text-coral">{run.errorMessage}</span>}
                      {run.effectiveStatus === "FAILED" && run.retryable === false && (
                        <span className="mt-3 block text-[11px] text-muted-foreground">
                          {run.errorCode?.includes("SCHEMA") || run.errorCode?.includes("CONTEXT")
                            ? "Renormalize with the active prepared-job-v2 contract."
                            : "Check or reactivate the exact embedded artifact in Model settings."}
                        </span>
                      )}
                      {(run.effectiveStatus === "FAILED" || run.effectiveStatus === "STALE") && run.retryable !== false && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="mt-3 min-h-9 cursor-pointer border-2 hover:border-purple hover:bg-purple/10"
                          disabled={busy}
                          onClick={(event) => {
                            event.stopPropagation();
                            void retryRun(run.id);
                          }}
                        >
                          <RefreshCw className="size-3" /> Retry
                        </Button>
                      )}
                    </div>
                  ))}
                  {!runs.isLoading && !runs.data?.some((run) => run.stage === "ranking") && (
                    <p className="text-sm text-muted-foreground">No ranking runs yet.</p>
                  )}
                </div>
              </BrutalCard>
            </aside>

            <div className="space-y-4">
              {runs.data?.some((run) => ["QUEUED", "RUNNING"].includes(run.effectiveStatus)) && (
                <BrutalCard className="border-purple bg-purple/10">
                  <p className="flex items-center gap-2 font-bold text-purple">
                    <LoaderCircle className="size-4 animate-spin" />
                    {runs.data.find((run) => ["QUEUED", "RUNNING"].includes(run.effectiveStatus))?.phase.replaceAll("_", " ")}
                  </p>
                  <p className="mt-2 text-sm text-muted-foreground">
                    The last successful result stays visible until this run commits completely.
                  </p>
                </BrutalCard>
              )}
              {rankings.isLoading ? (
                <Skeleton className="h-72 border-2 border-foreground" />
              ) : rankings.error ? (
                <ErrorPanel error={rankings.error} />
              ) : rankings.data?.length ? (
                <>
                  <div className="flex flex-wrap items-end justify-between gap-3 border-b-2 border-foreground pb-4">
                    <div>
                      <p className="ops-label text-acid">Top 25</p>
                      <h2 className="mt-2 text-3xl font-black uppercase">Model ranking</h2>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Rank badges remain the persisted model rank when you change the visual sort.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        aria-pressed={rankingSort === "preference"}
                        title="Sort by preference score"
                        className={`min-h-9 cursor-pointer border-2 px-3 text-xs transition hover:-translate-y-0.5 hover:border-acid ${rankingSort === "preference" ? "border-acid bg-acid/10 text-acid" : "bg-card"}`}
                        onClick={() => setRankingSort("preference")}
                      >
                        <ArrowDownWideNarrow className="size-3.5" /> Score
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        aria-pressed={rankingSort === "probability"}
                        title="Sort by apply probability"
                        className={`min-h-9 cursor-pointer border-2 px-3 text-xs transition hover:-translate-y-0.5 hover:border-purple ${rankingSort === "probability" ? "border-purple bg-purple/10 text-purple" : "bg-card"}`}
                        onClick={() => setRankingSort("probability")}
                      >
                        <ArrowDownWideNarrow className="size-3.5" /> Apply %
                      </Button>
                      <p className="w-full text-right font-mono text-[10px] text-muted-foreground">
                        {rankings.data.length} persisted · showing {Math.min(rankings.data.length, 25)}
                      </p>
                    </div>
                  </div>
                  <div className="space-y-4 py-2">
                    {sortedRankings.slice(0, 25).map((ranking, index) => {
                      const job = jobs.find((item) => item.id === ranking.jobId);
                      const fallback = ranking.modelApplyDecision === false;
                      const preferenceScore = ranking.rankingScore ?? ranking.jediPreferenceScore;
                      return (
                        <BrutalCard
                          key={ranking.jobId}
                          style={rankingGlow(index)}
                          className={`grid items-center gap-4 bg-card p-4 transition hover:-translate-y-0.5 md:grid-cols-[3rem_6rem_minmax(13rem,1fr)_minmax(11rem,14rem)_auto] ${rankingCardClass(index)}`}
                        >
                          <div className={`text-3xl font-black ${rankClass(index)}`}>#{ranking.rank}</div>
                          <PreferenceGauge score={preferenceScore} />
                          <div className="min-w-0">
                            <p className="ops-label truncate text-purple">{job?.companyName ?? ranking.jobId}</p>
                            {job ? (
                              <Link href={`/jobs/${job.id}`} className="block hover:text-acid">
                                <h3 className="mt-1 truncate text-lg font-black uppercase">{job.roleTitle}</h3>
                              </Link>
                            ) : (
                              <h3 className="mt-1 truncate text-lg font-black uppercase">Stored job</h3>
                            )}
                            <div className="mt-2 flex flex-wrap items-center gap-2">
                              <span className={`rounded-full border px-3 py-1 text-[10px] font-black uppercase ${ranking.applyRecommendation ? "border-acid/50 bg-acid/10 text-acid" : "border-coral/50 bg-coral/10 text-coral"}`}>
                                {ranking.applyRecommendation ? "Apply" : "Do not apply"}
                              </span>
                              {fallback && <span className="text-[10px] font-bold uppercase text-coral">Below threshold</span>}
                            </div>
                          </div>
                          <ProbabilityBar
                            probability={ranking.applyPreferenceProbability}
                            threshold={ranking.applyThreshold ?? 0.6}
                          />
                          {job && (
                            <a href={job.applyUrl} target="_blank" rel="noreferrer" className="grid size-10 cursor-pointer place-items-center rounded-lg border border-border text-muted-foreground transition hover:border-acid hover:bg-acid/10 hover:text-acid" aria-label={`Open ${job.roleTitle} source`}>
                              <ArrowUpRight className="size-4" />
                            </a>
                          )}
                          {ranking.componentScores && <FitBreakdown scores={ranking.componentScores} />}
                        </BrutalCard>
                      );
                    })}
                  </div>
                </>
              ) : (
                <BrutalCard className="bg-raised text-center">
                  <ChartNoAxesCombined className="mx-auto size-8 text-purple" />
                  <h2 className="mt-4 text-2xl font-black uppercase">No successful ranking yet</h2>
                  <p className="mt-2 text-sm text-muted-foreground">Normalize the batch, then run the active embedded model.</p>
                </BrutalCard>
              )}

              {session.data?.isGroupOwner && runs.data?.find((run) => run.id === successfulRunId)?.invocation && (
                <details className="border-2 border-border bg-raised p-4">
                  <summary className="ops-label cursor-pointer">Owner technical details</summary>
                  <pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap font-mono text-[10px]">
                    {JSON.stringify(runs.data.find((run) => run.id === successfulRunId)?.invocation, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        </section>
      )}

      <Dialog
        open={Boolean(action)}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setAction(undefined);
            setActionError(undefined);
          }
        }}
      >
        <DialogContent
          showCloseButton={!busy}
          className="rounded-[4px] border-2 border-foreground sm:max-w-lg"
        >
          {action && (
            <>
              <DialogHeader>
                <DialogTitle className="pr-10 text-2xl font-black uppercase">
                  {actionCopy[action].title}
                </DialogTitle>
                <DialogDescription className="leading-6">
                  {actionCopy[action].description}
                </DialogDescription>
              </DialogHeader>
              {Boolean(actionError) && <ErrorPanel error={actionError} />}
              <DialogFooter className="rounded-none">
                <Button
                  variant="outline"
                  className="min-h-11 border-2"
                  disabled={busy}
                  onClick={() => {
                    setAction(undefined);
                    setActionError(undefined);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  className={`min-h-11 rounded-lg border ${action === "delete" ? "border-coral/30 bg-coral/10 text-coral" : action === "rank" ? "border-purple/30 bg-purple/10 text-purple" : "border-border bg-foreground text-background"}`}
                  disabled={busy}
                  onClick={() => void runAction()}
                >
                  {busy ? "Working…" : actionCopy[action].confirm}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
