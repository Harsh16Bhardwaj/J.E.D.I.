"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import {
  Ban,
  CheckCircle2,
  ExternalLink,
  ListChecks,
  Play,
  RefreshCw,
  RotateCcw,
  Square,
} from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { RouteHeader } from "@/components/route-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  apiRequest,
  errorSummary,
  isApiError,
  type ScrapeAttemptPage,
  type ScrapeCandidateDetail,
  type ScrapeCandidatePage,
  type ScrapeImportResult,
  type ScrapeRunPage,
  type ScrapeRunStats,
  type ScrapeRunSummary,
  type ScrapeSource,
  type ScraperConfigSummary,
  type SourceDiscoveryRun,
  type User,
} from "@/lib/api";
import {
  canAdvanceScrape,
  canCancelScrape,
  canImportScrape,
  canSelectScrapeCandidate,
  experienceLabel,
  scrapeProgress,
  shouldWarnAboutPartialRun,
} from "@/lib/scraper-state";

function tone(status: string): "ready" | "queued" | "warning" | "offline" {
  if (status === "IMPORTED" || status === "REVIEW_READY") return "ready";
  if (status === "FAILED" || status === "CANCELLED" || status === "NORMALIZATION_FAILED") return "warning";
  if (["CREATED", "RUNNING", "IMPORTING", "NORMALIZING"].includes(status)) {
    return "queued";
  }
  return "offline";
}

const reviewLabels: Record<string, string> = {
  RECOMMENDED: "Recommended",
  NEEDS_REVIEW: "Owner review",
  REJECTED: "Cannot import",
};

const freshnessLabels: Record<string, string> = {
  VERIFIED_RECENT: "verified recent date",
  REVIEW_RECENT: "date needs review",
  REJECTED: "date unavailable or stale",
};

function reasonLabel(reason: string): string {
  return reason
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (letter) => letter.toUpperCase());
}

export default function ScraperPage() {
  const { mutate: mutateGlobal } = useSWRConfig();
  const session = useSWR<User>("/api/auth/me");
  const config = useSWR<ScraperConfigSummary>("/api/scraper/config");
  const sources = useSWR<ScrapeSource[]>("/api/scraper/sources");
  const runs = useSWR<ScrapeRunPage>("/api/scraper/runs?page=1&pageSize=20");
  const sourceRefresh = useSWR<SourceDiscoveryRun | null>("/api/scraper/source-refresh");
  const [runId, setRunId] = useState<string>();
  const [working, setWorking] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [stoppingForReview, setStoppingForReview] = useState(false);
  const [cancellingSourceRefresh, setCancellingSourceRefresh] = useState(false);
  const cancelRequested = useRef(false);
  const sourceCancelRequested = useRef(false);
  const selectionQueue = useRef(new Map<string, boolean>());
  const selectionTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const selectionSync = useRef<Promise<void>>(Promise.resolve());
  const [partialConfirmed, setPartialConfirmed] = useState(false);
  const [importResult, setImportResult] = useState<ScrapeImportResult>();
  const [sourceUrl, setSourceUrl] = useState("");
  const [candidatePage, setCandidatePage] = useState(1);
  const [expandedCandidateId, setExpandedCandidateId] = useState<string>();
  const [selectionSaving, setSelectionSaving] = useState(false);
  const [bulkSelection, setBulkSelection] = useState(false);
  const selectedRunId = runId ?? runs.data?.items[0]?.id;
  const detail = useSWR<ScrapeRunSummary>(
    selectedRunId ? `/api/scraper/runs/${selectedRunId}` : null,
  );
  const loadReviewData = Boolean(
    detail.data && !["CREATED", "RUNNING"].includes(detail.data.status),
  );
  const attempts = useSWR<ScrapeAttemptPage>(
    selectedRunId && loadReviewData
      ? `/api/scraper/runs/${selectedRunId}/attempts?page=1&pageSize=100`
      : null,
  );
  const candidates = useSWR<ScrapeCandidatePage>(
    selectedRunId && loadReviewData
      ? `/api/scraper/runs/${selectedRunId}/candidates?page=${candidatePage}&pageSize=100`
      : null,
  );
  const runStats = useSWR<ScrapeRunStats>(
    selectedRunId && loadReviewData
      ? `/api/scraper/runs/${selectedRunId}/stats`
      : null,
  );
  const expandedCandidate = useSWR<ScrapeCandidateDetail>(
    selectedRunId && expandedCandidateId
      ? `/api/scraper/runs/${selectedRunId}/candidates/${expandedCandidateId}`
      : null,
  );

  async function refresh(next?: ScrapeRunSummary) {
    if (next) {
      await mutateGlobal(`/api/scraper/runs/${next.id}`, next, {
        revalidate: false,
      });
    }
    // Keep control requests responsive on the small local/hosted DB pool.
    // These payloads are review-only and do not need to fan out concurrently.
    await runs.mutate();
    await attempts.mutate();
    await candidates.mutate();
    await runStats.mutate();
  }

  async function createRun() {
    if (working) return;
    setWorking(true);
    cancelRequested.current = false;
    setImportResult(undefined);
    try {
      const created = await apiRequest<ScrapeRunSummary>("/api/scraper/runs", {
        method: "POST",
      });
      setRunId(created.id);
      await mutateGlobal(`/api/scraper/runs/${created.id}`, created, {
        revalidate: false,
      });
      toast.success("Collection started.");
      await collectRun(created);
    } catch (error) {
      if (
        isApiError(error) &&
        error.code === "SCRAPER_RUN_ACTIVE" &&
        error.details &&
        typeof error.details === "object" &&
        "runId" in error.details &&
        typeof error.details.runId === "string"
      ) {
        setRunId(error.details.runId);
        const existing = await apiRequest<ScrapeRunSummary>(
          `/api/scraper/runs/${error.details.runId}`,
        );
        await mutateGlobal(`/api/scraper/runs/${existing.id}`, existing, {
          revalidate: false,
        });
        toast.info("Resuming the existing scraper run.");
        if (canAdvanceScrape(existing)) await collectRun(existing);
        return;
      }
      toast.error(errorSummary(error));
    } finally {
      setWorking(false);
    }
  }

  async function addSource() {
    if (!sourceUrl.trim() || working) return;
    setWorking(true);
    try {
      const created = await apiRequest<ScrapeSource>("/api/scraper/sources", {
        method: "POST",
        body: JSON.stringify({ url: sourceUrl.trim() }),
      });
      setSourceUrl("");
      await sources.mutate();
      toast.success(`${created.name} source added.`, {
        description: `Future runs will poll its ${created.atsType} board directly.`,
      });
    } catch (error) {
      toast.error(errorSummary(error));
    } finally {
      setWorking(false);
    }
  }

  async function setSourceActive(source: ScrapeSource, active: boolean) {
    try {
      await apiRequest<ScrapeSource>(`/api/scraper/sources/${source.id}`, {
        method: "PATCH",
        body: JSON.stringify({ active }),
      });
      await sources.mutate();
    } catch (error) {
      toast.error(errorSummary(error));
    }
  }

  async function sourceAction(source: ScrapeSource, action: "revalidate" | "clear-cooldown") {
    try {
      await apiRequest<ScrapeSource>(`/api/scraper/sources/${source.id}/${action}`, {
        method: "POST",
      });
      await sources.mutate();
      toast.success(action === "revalidate" ? "Source revalidated." : "Cooldown cleared.");
    } catch (error) {
      toast.error(errorSummary(error));
    }
  }

  async function refreshSources() {
    if (working) return;
    setWorking(true);
    sourceCancelRequested.current = false;
    try {
      let next = sourceRefresh.data;
      if (!next || !["CREATED", "RUNNING"].includes(next.status)) {
        next = await apiRequest<SourceDiscoveryRun>("/api/scraper/source-refresh", {
          method: "POST",
        });
      }
      for (
        let chunk = 0;
        chunk < 250 &&
        !sourceCancelRequested.current &&
        ["CREATED", "RUNNING"].includes(next.status);
        chunk += 1
      ) {
        next = await apiRequest<SourceDiscoveryRun>(
          `/api/scraper/source-refresh/${next.id}/advance`,
          { method: "POST" },
        );
        await sourceRefresh.mutate(next, { revalidate: false });
      }
      await Promise.all([sourceRefresh.mutate(), sources.mutate()]);
      if (next.status === "COMPLETED") {
        toast.success(`Source refresh complete: ${next.activatedSources} boards activated.`);
      }
    } catch (error) {
      toast.error(errorSummary(error));
      await sourceRefresh.mutate();
    } finally {
      setWorking(false);
    }
  }

  async function cancelSourceRefresh() {
    if (!sourceRefresh.data || cancellingSourceRefresh) return;
    sourceCancelRequested.current = true;
    setCancellingSourceRefresh(true);
    try {
      const next = await apiRequest<SourceDiscoveryRun>(
        `/api/scraper/source-refresh/${sourceRefresh.data.id}/cancel`,
        { method: "POST" },
      );
      await sourceRefresh.mutate(next, { revalidate: false });
      toast.success("Source refresh cancelled.");
    } catch (error) {
      toast.error(errorSummary(error));
      await sourceRefresh.mutate();
    } finally {
      setCancellingSourceRefresh(false);
    }
  }

  async function collectRun(
    selectedRun: ScrapeRunSummary,
    options: { retryFailed?: boolean; resume?: boolean } = {},
  ) {
    cancelRequested.current = false;
    let next = selectedRun;
    if (options.retryFailed) {
      next = await apiRequest<ScrapeRunSummary>(
        `/api/scraper/runs/${next.id}/retry-failed`,
        { method: "POST" },
      );
    } else if (options.resume) {
      next = await apiRequest<ScrapeRunSummary>(
        `/api/scraper/runs/${next.id}/resume`,
        { method: "POST" },
      );
    }
    let chunks = 0;
    while (
      canAdvanceScrape(next) &&
      !cancelRequested.current &&
      chunks < 250
    ) {
      const concurrent = Math.max(1, config.data?.concurrentSources ?? 3);
      const summaries = await Promise.all(
        Array.from({ length: concurrent }, () =>
          apiRequest<ScrapeRunSummary>(`/api/scraper/runs/${next.id}/advance`, {
            method: "POST",
          }),
        ),
      );
      next = summaries.reduce((latest, candidate) =>
        new Date(candidate.updatedAt) > new Date(latest.updatedAt)
          ? candidate
          : latest,
      );
      await mutateGlobal(`/api/scraper/runs/${next.id}`, next, {
        revalidate: false,
      });
      chunks += concurrent;
    }
    next = await apiRequest<ScrapeRunSummary>(`/api/scraper/runs/${next.id}`);
    await refresh(next);
    if (next.status === "REVIEW_READY") {
      toast.success("Collection stopped. Candidates are ready to review.");
    }
    if (next.status === "FAILED") {
      toast.error(next.errorMessage ?? "The run failed.");
    }
  }

  async function advance(retryFailed = false, resume = false) {
    const selectedRun = detail.data;
    if (!selectedRun || working) return;
    setWorking(true);
    try {
      await collectRun(selectedRun, { retryFailed, resume });
    } catch (error) {
      toast.error(errorSummary(error));
      await detail.mutate();
    } finally {
      setWorking(false);
    }
  }

  async function stopAndReview() {
    if (!detail.data || stoppingForReview) return;
    cancelRequested.current = true;
    setStoppingForReview(true);
    try {
      const next = await apiRequest<ScrapeRunSummary>(
        `/api/scraper/runs/${detail.data.id}/stop-and-review`,
        { method: "POST" },
      );
      await refresh(next);
      toast.success("Collection stopped. Review and select any importable job.");
    } catch (error) {
      toast.error(errorSummary(error));
      await detail.mutate();
    } finally {
      setStoppingForReview(false);
    }
  }

  function flushSelectionQueue() {
    if (!detail.data || selectionQueue.current.size === 0) return;
    const runIdToUpdate = detail.data.id;
    const changes = [...selectionQueue.current.entries()];
    selectionQueue.current.clear();
    selectionTimer.current = null;
    selectionSync.current = selectionSync.current
      .then(async () => {
        let next: ScrapeRunSummary | undefined;
        for (const selected of [true, false]) {
          const candidateIds = changes
            .filter(([, value]) => value === selected)
            .map(([candidateId]) => candidateId);
          if (!candidateIds.length) continue;
          next = await apiRequest<ScrapeRunSummary>(
            `/api/scraper/runs/${runIdToUpdate}/selection`,
            {
              method: "PATCH",
              body: JSON.stringify({ candidateIds, selected }),
            },
          );
        }
        if (next && selectionQueue.current.size === 0) {
          await detail.mutate(next, { revalidate: false });
        }
      })
      .catch(async (error) => {
        toast.error(errorSummary(error));
        await Promise.all([detail.mutate(), candidates.mutate()]);
      })
      .finally(() => {
        if (selectionQueue.current.size > 0) {
          if (selectionTimer.current) clearTimeout(selectionTimer.current);
          selectionTimer.current = setTimeout(flushSelectionQueue, 100);
        } else {
          setSelectionSaving(false);
        }
      });
  }

  function updateSelection(candidateId: string, selected: boolean) {
    if (!detail.data) return;
    const current = candidates.data?.items.find((item) => item.id === candidateId);
    if (!current || current.selected === selected) return;
    selectionQueue.current.set(candidateId, selected);
    setSelectionSaving(true);
    void candidates.mutate(
      (page) =>
        page
          ? {
              ...page,
              items: page.items.map((item) =>
                item.id === candidateId ? { ...item, selected } : item,
              ),
            }
          : page,
      { revalidate: false },
    );
    void detail.mutate(
      (run) =>
        run
          ? {
              ...run,
              selectedCount: Math.max(
                0,
                Math.min(run.validCount, run.selectedCount + (selected ? 1 : -1)),
              ),
            }
          : run,
      { revalidate: false },
    );
    if (selectionTimer.current) clearTimeout(selectionTimer.current);
    selectionTimer.current = setTimeout(flushSelectionQueue, 100);
  }

  async function updateAllSelection(selected: boolean) {
    if (!detail.data || bulkSelection) return;
    const runToUpdate = detail.data;
    if (selectionTimer.current) clearTimeout(selectionTimer.current);
    flushSelectionQueue();
    setBulkSelection(true);
    setSelectionSaving(true);
    void candidates.mutate(
      (page) =>
        page
          ? {
              ...page,
              items: page.items.map((candidate) => ({
                ...candidate,
                selected: selected
                  ? canSelectScrapeCandidate(candidate, runToUpdate.status)
                  : false,
              })),
            }
          : page,
      { revalidate: false },
    );
    void detail.mutate(
      (run) =>
        run ? { ...run, selectedCount: selected ? run.validCount : 0 } : run,
      { revalidate: false },
    );
    try {
      await selectionSync.current;
      const next = await apiRequest<ScrapeRunSummary>(
        `/api/scraper/runs/${runToUpdate.id}/selection/all`,
        {
          method: "PATCH",
          body: JSON.stringify({ selected }),
        },
      );
      await Promise.all([
        detail.mutate(next, { revalidate: false }),
        candidates.mutate(),
      ]);
      toast.success(
        selected
          ? `${next.selectedCount} importable jobs selected.`
          : "All selections cleared.",
      );
    } catch (error) {
      toast.error(errorSummary(error));
      await Promise.all([detail.mutate(), candidates.mutate()]);
    } finally {
      setBulkSelection(false);
      setSelectionSaving(false);
    }
  }

  async function cancelRun() {
    if (!detail.data || cancelling) return;
    cancelRequested.current = true;
    setCancelling(true);
    try {
      const next = await apiRequest<ScrapeRunSummary>(
        `/api/scraper/runs/${detail.data.id}/cancel`,
        { method: "POST" },
      );
      await refresh(next);
      toast.success("Scraper run cancelled.");
    } catch (error) {
      toast.error(errorSummary(error));
    } finally {
      setCancelling(false);
    }
  }

  async function importSelected() {
    if (!detail.data || working) return;
    setWorking(true);
    try {
      if (selectionTimer.current) clearTimeout(selectionTimer.current);
      flushSelectionQueue();
      await selectionSync.current;
      const result = await apiRequest<ScrapeImportResult>(
        `/api/scraper/runs/${detail.data.id}/import`,
        {
          method: "POST",
          body: JSON.stringify({ confirmPartial: partialConfirmed }),
        },
      );
      setImportResult(result);
      await detail.mutate();
      await runs.mutate();
      toast.success("Selected jobs imported and normalized to INR.");
    } catch (error) {
      toast.error(errorSummary(error));
      await Promise.all([detail.mutate(), runs.mutate()]);
    } finally {
      setWorking(false);
    }
  }

  async function retryNormalization() {
    if (!detail.data || working) return;
    setWorking(true);
    try {
      const result = await apiRequest<ScrapeImportResult>(
        `/api/scraper/runs/${detail.data.id}/retry-normalization`,
        { method: "POST" },
      );
      setImportResult(result);
      await Promise.all([detail.mutate(), runs.mutate()]);
      toast.success("Normalization completed.");
    } catch (error) {
      toast.error(errorSummary(error));
      await detail.mutate();
    } finally {
      setWorking(false);
    }
  }

  if (session.data && !session.data.isGroupOwner) {
    return (
      <BrutalCard className="border-coral">
        <p className="ops-label text-coral">Owner access required</p>
        <p className="mt-3 text-sm text-muted-foreground">
          The scraper workspace is available only to the group owner.
        </p>
      </BrutalCard>
    );
  }

  const run = detail.data;
  const progress = run ? scrapeProgress(run) : 0;
  const runAttempts = loadReviewData ? (attempts.data?.items ?? []) : [];
  const runCandidates = loadReviewData ? (candidates.data?.items ?? []) : [];
  const visibleRunStats = loadReviewData ? runStats.data : undefined;
  const partialRun = run ? shouldWarnAboutPartialRun(run) : false;
  const stageIndex = run
    ? ["CREATED", "RUNNING"].includes(run.status)
      ? 0
      : run.status === "REVIEW_READY"
        ? 1
        : ["IMPORTING", "NORMALIZING", "NORMALIZATION_FAILED"].includes(
              run.status,
            )
          ? 2
          : run.status === "IMPORTED"
            ? 3
            : -1
    : -1;

  return (
    <div className="space-y-9">
      <RouteHeader
        eyebrow="Owner collection workspace"
        title="Collect, inspect, then import."
        path="/scraper"
        description="Manual, resumable employer-direct collection with evidence-backed enrichment and INR normalization."
      />
      <div className="-mt-5 inline-flex rounded border border-purple bg-purple/10 px-2 py-1 font-mono text-[11px] font-bold uppercase tracking-wider text-purple">
        BETA
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.35fr_.65fr]">
        <BrutalCard>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="ops-label text-acid">Collection policy</p>
              <h2 className="mt-2 text-2xl font-black uppercase">
                {config.data?.targetJobCount ?? 60} trustworthy candidates
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                {config.data?.lookbackDays ?? 14}-day verified selection · up to {config.data?.reviewLookbackDays ?? 30} days for review · India and worldwide remote
              </p>
            </div>
            <Button onClick={createRun} disabled={working || !config.data}>
              <Play className="size-4" /> Run scraper
            </Button>
          </div>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-border p-4">
              <p className="text-2xl font-black">
                {sources.data?.length ?? config.data?.seededSourceCount ?? "—"}
              </p>
              <p className="ops-label mt-1 text-muted-foreground">Direct ATS sources</p>
            </div>
            <div className="rounded-lg border border-border p-4">
              <p className="text-2xl font-black">{config.data?.brightDataLimit ?? 150}</p>
              <p className="ops-label mt-1 text-muted-foreground">Provider cap</p>
            </div>
            <div className="rounded-lg border border-border p-4">
              <StatusBadge tone={config.data?.unlockerConfigured ? "ready" : "warning"}>
                Unlocker {config.data?.unlockerConfigured ? "ready" : "optional"}
              </StatusBadge>
              <p className="mt-2 text-xs text-muted-foreground">
                Direct ATS collection does not require Bright Data.
              </p>
            </div>
          </div>
          <div className="mt-6 border-t border-border pt-5">
            <p className="ops-label text-purple">Add another ATS board</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Paste a supported ATS or employer JobPosting JSON-LD page. Aggregator links are rejected.
            </p>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <Input
                value={sourceUrl}
                onChange={(event) => setSourceUrl(event.target.value)}
                placeholder="https://jobs.ashbyhq.com/company"
                aria-label="ATS careers URL"
                className="min-h-10 flex-1"
              />
              <Button
                variant="outline"
                disabled={working || !sourceUrl.trim()}
                onClick={addSource}
              >
                Add source
              </Button>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
            <div>
              <p className="ops-label text-acid">Refresh known companies</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {sourceRefresh.data
                  ? `${sourceRefresh.data.processedHints}/${sourceRefresh.data.totalHints} checked · ${sourceRefresh.data.activatedSources} activated`
                  : `${config.data?.companyHintCount ?? 135} employer domains ready`}
              </p>
            </div>
            <div className="flex gap-2">
              {sourceRefresh.data && ["CREATED", "RUNNING"].includes(sourceRefresh.data.status) && (
                <Button
                  variant="outline"
                  disabled={cancellingSourceRefresh}
                  onClick={cancelSourceRefresh}
                >
                  <Ban className="size-4" />
                  {cancellingSourceRefresh ? "Cancelling…" : "Cancel"}
                </Button>
              )}
              <Button variant="outline" disabled={working} onClick={refreshSources}>
                <RefreshCw className={`size-4 ${working ? "animate-spin" : ""}`} /> Refresh sources
              </Button>
            </div>
          </div>
        </BrutalCard>

        <BrutalCard>
          <p className="ops-label text-purple">Run history</p>
          <div className="mt-4 max-h-56 space-y-2 overflow-auto">
            {runs.data?.items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                   setRunId(item.id);
                   setPartialConfirmed(false);
                   setImportResult(undefined);
                   setCandidatePage(1);
                }}
                className={`w-full rounded-lg border p-3 text-left transition-colors ${selectedRunId === item.id ? "border-purple bg-purple/10" : "border-border hover:bg-raised"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <StatusBadge tone={tone(item.status)}>{item.status}</StatusBadge>
                  <span className="font-mono text-xs">{item.validCount} importable</span>
                </div>
                <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                  {new Date(item.createdAt).toLocaleString()}
                </p>
              </button>
            ))}
            {!runs.data?.items.length && (
              <p className="text-sm text-muted-foreground">No scraper runs yet.</p>
            )}
          </div>
        </BrutalCard>
      </div>

      <BrutalCard>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="ops-label text-purple">Source health</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Yield-aware ordering, failures, and temporary cooldowns for every board.
            </p>
          </div>
          <span className="font-mono text-xs">{sources.data?.filter((source) => source.active).length ?? 0} active</span>
        </div>
        <div className="mt-4 max-h-72 divide-y divide-border overflow-auto rounded-lg border border-border">
          {sources.data?.map((source) => (
            <div key={source.id} className="flex flex-wrap items-center justify-between gap-3 p-3 text-sm">
              <div>
                <p className="font-bold">{source.name} <span className="font-normal text-muted-foreground">· {source.atsType}</span></p>
                <p className="text-xs text-muted-foreground">
                  {source.healthStatus} · {source.eligibleYield} eligible / {source.jobsScanned} scanned
                  {source.cooldownUntil ? ` · cooldown until ${new Date(source.cooldownUntil).toLocaleString()}` : ""}
                </p>
              </div>
              <div className="flex gap-2">
                {source.cooldownUntil && (
                  <Button size="sm" variant="outline" onClick={() => void sourceAction(source, "clear-cooldown")}>
                    Clear cooldown
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={() => void sourceAction(source, "revalidate")}>
                  Revalidate
                </Button>
                <Button size="sm" variant="outline" onClick={() => void setSourceActive(source, !source.active)}>
                  {source.active ? "Disable" : "Enable"}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </BrutalCard>

      {run && (
        <>
          <BrutalCard>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <StatusBadge tone={tone(run.status)}>{run.status}</StatusBadge>
                <p className="mt-3 font-mono text-xs text-muted-foreground">{run.id}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {canAdvanceScrape(run) && (
                  <Button disabled={working} onClick={() => void advance()}>
                    <RefreshCw className={`size-4 ${working ? "animate-spin" : ""}`} />
                    {working
                      ? "Collecting sources…"
                      : run.status === "CREATED"
                        ? "Start collection"
                        : "Resume collection"}
                  </Button>
                )}
                {run.status === "RUNNING" && (
                  <Button
                    variant="outline"
                    disabled={stoppingForReview}
                    onClick={stopAndReview}
                  >
                    <CheckCircle2 className="size-4" />
                    {stoppingForReview ? "Stopping…" : "Stop & review results"}
                  </Button>
                )}
                {run.status === "REVIEW_READY" &&
                  run.processedSourceCount < run.sourceCount && (
                    <Button
                      variant="outline"
                      disabled={working}
                      onClick={() => void advance(false, true)}
                    >
                      <RefreshCw className={`size-4 ${working ? "animate-spin" : ""}`} />
                      Continue collection
                    </Button>
                  )}
                {run.status === "NORMALIZATION_FAILED" && (
                  <Button disabled={working} onClick={retryNormalization}>
                    <RotateCcw className="size-4" /> Retry normalization
                  </Button>
                )}
                {run.status === "NORMALIZING" && !working && (
                  <Button onClick={retryNormalization}>
                    <RotateCcw className="size-4" /> Resume normalization
                  </Button>
                )}
                {run.status === "IMPORTING" && !working && (
                  <Button onClick={importSelected}>
                    <RotateCcw className="size-4" /> Resume import
                  </Button>
                )}
                {run.failedSourceCount > 0 &&
                  run.processedSourceCount >= run.sourceCount &&
                  ["REVIEW_READY", "FAILED"].includes(run.status) && (
                  <Button variant="outline" disabled={working} onClick={() => void advance(true)}>
                    <RotateCcw className="size-4" /> Retry failed sources
                  </Button>
                )}
                {canCancelScrape(run) && (
                  <Button
                    variant="outline"
                    disabled={cancelling}
                    onClick={cancelRun}
                  >
                    <Ban className="size-4" />
                    {cancelling ? "Cancelling…" : "Cancel run"}
                  </Button>
                )}
              </div>
            </div>
            <div className="mt-6 grid gap-2 md:grid-cols-4">
              {["1. Collect", "2. Review & select", "3. Import & normalize", "4. Rank manually"].map(
                (label, index) => (
                  <div
                    key={label}
                    className={`rounded border px-3 py-2 text-xs font-bold uppercase ${
                      index === stageIndex
                        ? "border-acid bg-acid/10 text-acid"
                        : index < stageIndex
                          ? "border-border text-foreground"
                          : "border-border text-muted-foreground"
                    }`}
                  >
                    {label}
                  </div>
                ),
              )}
            </div>
            <div className="mt-6 h-3 overflow-hidden rounded-full border border-border bg-raised">
              <div className="h-full bg-acid transition-all" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {run.processedSourceCount}/{run.sourceCount} sources processed · {progress}%
              {run.status === "RUNNING"
                ? " · Review unlocks when collection finishes, or choose Stop & review results now."
                : run.stoppedEarly
                  ? " · Collection was stopped early; review now or continue later."
                  : ""}
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-6">
              {[
                ["Importable", run.validCount],
                ["Selected", run.selectedCount],
                ["Jobs seen", run.discoveredCount],
                ["Source failures", run.failedSourceCount],
                ["Direct requests", run.freeRequestCount],
                ["Bright Data", `${run.brightDataUsed}/${run.brightDataLimit}`],
              ].map(([label, value]) => (
                <div key={label}>
                  <p className="text-xl font-black">{value}</p>
                  <p className="ops-label mt-1 text-muted-foreground">{label}</p>
                </div>
              ))}
            </div>
            <p className="mt-4 text-xs text-muted-foreground">{run.providerUsageReason}</p>
            {visibleRunStats && (
              <div className="mt-4 grid gap-3 border-t border-border pt-4 md:grid-cols-2">
                <div>
                  <p className="ops-label text-purple">Yield by ATS</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {Object.entries(visibleRunStats.byAts)
                      .map(([ats, counts]) => `${ats}: ${counts.recommended} recommended / ${counts.needsReview} owner review / ${counts.rejected} cannot import`)
                      .join(" · ") || "No candidates staged yet."}
                  </p>
                </div>
                <div>
                  <p className="ops-label text-coral">Top review and blocking notes</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {Object.entries(visibleRunStats.byRejectionReason)
                      .sort((left, right) => right[1] - left[1])
                      .slice(0, 5)
                      .map(([reason, count]) => `${reasonLabel(reason)}: ${count}`)
                      .join(" · ") || "No review notes recorded."}
                  </p>
                </div>
              </div>
            )}
            {run.errorMessage && <p className="mt-4 text-sm text-coral">{run.errorMessage}</p>}
          </BrutalCard>

          {run.status === "REVIEW_READY" && (
            <BrutalCard className="border-acid bg-acid/5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="ops-label text-acid">Choose jobs to import</p>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Select every importable job at once, or adjust individual checkboxes below.
                  </p>
                </div>
                <p className="font-mono text-sm font-bold">
                  {run.selectedCount} / {run.validCount} selected
                </p>
              </div>
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <Button
                  disabled={bulkSelection || run.selectedCount >= run.validCount}
                  onClick={() => void updateAllSelection(true)}
                >
                  <ListChecks className="size-4" /> Select all {run.validCount} importable
                </Button>
                <Button
                  variant="outline"
                  disabled={bulkSelection || run.selectedCount === 0}
                  onClick={() => void updateAllSelection(false)}
                >
                  <Square className="size-4" /> Clear all
                </Button>
                <span aria-live="polite" className="text-xs text-muted-foreground">
                  {selectionSaving ? "Saving selection…" : "Selection saved"}
                </span>
              </div>
              <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-border pt-5">
                {partialRun ? (
                  <label className="flex max-w-xl items-start gap-3 text-sm text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={partialConfirmed}
                      onChange={(event) => setPartialConfirmed(event.target.checked)}
                      className="mt-0.5 size-4 accent-[#b7ff2a]"
                    />
                    This is a partial collection. Import the selected jobs without waiting for
                    the remaining sources.
                  </label>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Collection is complete. Import only the jobs currently selected.
                  </p>
                )}
                <Button
                  disabled={
                    working ||
                    selectionSaving ||
                    !canImportScrape(run) ||
                    (partialRun && !partialConfirmed)
                  }
                  onClick={importSelected}
                >
                  <CheckCircle2 className="size-4" /> Import {run.selectedCount} selected
                </Button>
              </div>
            </BrutalCard>
          )}

          {["CREATED", "RUNNING"].includes(run.status) && (
            <BrutalCard className="border-purple bg-purple/5">
              <p className="ops-label text-purple">Collection stage</p>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">
                Candidate selection and import are intentionally locked while sources are
                changing. Let all sources finish, or use <strong>Stop & review results</strong>
                to freeze the current set without discarding it.
              </p>
            </BrutalCard>
          )}

          {runAttempts.some((attempt) => attempt.errorMessage) && (
            <BrutalCard className="border-coral">
              <p className="ops-label text-coral">Source errors</p>
              <div className="mt-4 space-y-3">
                {runAttempts
                  .filter((attempt) => attempt.errorMessage)
                  .map((attempt) => (
                    <div key={attempt.id} className="rounded-lg border border-coral/30 p-3 text-sm">
                      <strong>{attempt.sourceKey}</strong>
                      <p className="mt-1 text-muted-foreground">{attempt.errorMessage}</p>
                    </div>
                  ))}
              </div>
            </BrutalCard>
          )}

          {runCandidates.length > 0 && (
            <BrutalCard className="overflow-hidden p-0">
              <div className="border-b border-border p-5">
                <p className="ops-label text-acid">Candidate review</p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Recommended jobs are selected automatically. Owner-review jobs are also
                  importable and can be selected manually—including senior, high-experience,
                  or non-India roles. The ranker decides fit after import. “Cannot import” is
                  reserved for missing/stale dates, invalid vacancy URLs, duplicates, or closed
                  applications.
                </p>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Select</TableHead>
                    <TableHead>Company / role</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead>Experience</TableHead>
                    <TableHead>Posted</TableHead>
                    <TableHead>ATS</TableHead>
                    <TableHead>URL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runCandidates.map((candidate) => (
                    <TableRow key={candidate.id}>
                      <TableCell>
                        <input
                          aria-label={`Select ${candidate.roleTitle}`}
                          type="checkbox"
                          checked={candidate.selected}
                          disabled={
                            !canSelectScrapeCandidate(candidate, run.status)
                          }
                          onChange={(event) =>
                            void updateSelection(candidate.id, event.target.checked)
                          }
                          className="size-4 accent-[#b7ff2a]"
                        />
                      </TableCell>
                      <TableCell>
                        <p className="font-bold">{candidate.companyName}</p>
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedCandidateId(
                              expandedCandidateId === candidate.id ? undefined : candidate.id,
                            )
                          }
                          className="max-w-72 text-left text-muted-foreground hover:underline"
                        >
                          {candidate.roleTitle}
                        </button>
                        <p className="mt-1 text-[10px] uppercase text-muted-foreground">
                          {reviewLabels[candidate.reviewGroup]} · source quality {candidate.qualityScore.toFixed(0)} · {freshnessLabels[candidate.freshnessTier] ?? reasonLabel(candidate.freshnessTier)}
                        </p>
                        {expandedCandidateId === candidate.id && (
                          <div className="mt-3 max-w-xl rounded border border-border bg-raised p-3 text-xs">
                            <p className="font-bold">Extracted evidence</p>
                            <p className="mt-1 text-muted-foreground">
                              {candidate.qualityFailures.length
                                ? candidate.qualityFailures.map(reasonLabel).join(" · ")
                                : "No review notes."}
                            </p>
                            {expandedCandidate.data?.evidenceSpans.slice(0, 8).map((span, index) => (
                              <p key={`${span.field}-${index}`} className="mt-1">
                                <strong>{span.field}:</strong> “{span.text}”
                              </p>
                            ))}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>{candidate.location ?? "Unknown"}</TableCell>
                      <TableCell>
                        {experienceLabel(
                          candidate.experienceMinYears,
                          candidate.experienceMaxYears,
                        )}
                      </TableCell>
                      <TableCell>
                        {candidate.postedAt
                          ? new Date(candidate.postedAt).toLocaleDateString()
                          : "Unknown"}
                      </TableCell>
                      <TableCell>
                        <p>{candidate.atsType}</p>
                        <p className="text-[10px] uppercase text-muted-foreground">
                          {candidate.geographyEligibility}
                        </p>
                      </TableCell>
                      <TableCell>
                        <a
                          href={candidate.sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`Open ${candidate.roleTitle}`}
                          className="text-acid hover:underline"
                        >
                          <ExternalLink className="size-4" />
                        </a>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {(candidates.data?.total ?? 0) > 100 && (
                <div className="flex items-center justify-between border-t border-border px-5 py-3">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={candidatePage <= 1}
                    onClick={() => setCandidatePage((page) => Math.max(1, page - 1))}
                  >
                    Previous 100
                  </Button>
                  <span className="font-mono text-xs text-muted-foreground">
                    Page {candidatePage} of {Math.ceil((candidates.data?.total ?? 0) / 100)}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={candidatePage * 100 >= (candidates.data?.total ?? 0)}
                    onClick={() => setCandidatePage((page) => page + 1)}
                  >
                    Next 100
                  </Button>
                </div>
              )}
            </BrutalCard>
          )}

          {(importResult || (run.importedBatchId && run.status === "IMPORTED")) && (
            <BrutalCard className="border-acid bg-acid/5">
              <p className="ops-label text-acid">Import complete</p>
              <p className="mt-3 text-sm text-muted-foreground">
                The scraper created and INR-normalized a normal batch. It has not been ranked or
                emailed.
              </p>
              <Button
                className="mt-5"
                render={
                  <Link href={`/batches/${importResult?.batch.batchId ?? run.importedBatchId}`} />
                }
              >
                Open imported batch <ExternalLink className="size-4" />
              </Button>
            </BrutalCard>
          )}
        </>
      )}
    </div>
  );
}
