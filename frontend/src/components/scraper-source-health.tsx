"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/status-badge";
import { apiRequest, errorSummary, type ScrapeSource } from "@/lib/api";

type SourceAction = "revalidate" | "clear-cooldown" | "toggle";

function SourceRow({
  source,
  onChange,
  onOpenRun,
}: {
  source: ScrapeSource;
  onChange: () => void;
  onOpenRun?: (id: string) => void;
}) {
  const [pending, setPending] = useState<SourceAction>();
  const [message, setMessage] = useState<{ text: string; error?: boolean }>();
  const history = source.recentRuns ?? [];
  const failures = history.filter((run) => run.status === "FAILED").length;
  const status = !source.active ? "Disabled" : ({
    HEALTHY: source.jobsScanned === 0 ? "Healthy · zero jobs" : "Healthy",
    FAILING: "Failing",
    COOLDOWN: "Cooldown",
    UNKNOWN: "Unchecked",
  }[source.healthStatus] ?? source.healthStatus);

  async function act(action: SourceAction) {
    if (pending) return;
    setPending(action);
    setMessage(undefined);
    try {
      const path = `/api/scraper/sources/${source.id}`;
      await apiRequest<ScrapeSource>(action === "toggle" ? path : `${path}/${action}`, {
        method: action === "toggle" ? "PATCH" : "POST",
        body: action === "toggle" ? JSON.stringify({ active: !source.active }) : undefined,
        signal: AbortSignal.timeout(60_000),
      });
      setMessage({ text: "Source updated." });
    } catch (error) {
      setMessage({ text: errorSummary(error), error: true });
    } finally {
      onChange();
      setPending(undefined);
    }
  }

  return (
    <div className="space-y-2 p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-bold">{source.name} <span className="font-normal text-muted-foreground">· {source.atsType}</span></p>
          <p className="mt-1 text-xs text-muted-foreground">
            {history.length ? `${failures} failures in ${history.length} recent collection outcomes` : "No completed collection history"}
            {source.consecutiveFailures > 0 && ` · ${source.consecutiveFailures} consecutive failures`}
            {source.lastSuccessAt && ` · last success ${new Date(source.lastSuccessAt).toLocaleString()}`}
          </p>
          {source.cooldownUntil && (
            <p className="text-xs text-muted-foreground">
              {source.consecutiveFailures >= 3 ? "Repeated failures" : "Cooldown"} · eligible after {new Date(source.cooldownUntil).toLocaleString()}
            </p>
          )}
        </div>
        <StatusBadge tone={!source.active ? "offline" : source.healthStatus === "HEALTHY" ? "ready" : source.healthStatus === "UNKNOWN" ? "offline" : "warning"}>
          {status}
        </StatusBadge>
      </div>
      <div className="flex flex-wrap gap-2">
        {source.cooldownUntil && (
          <Button size="sm" variant="outline" disabled={Boolean(pending)} onClick={() => void act("clear-cooldown")}>
            {pending === "clear-cooldown" ? "Clearing…" : "Clear cooldown"}
          </Button>
        )}
        <Button size="sm" variant="outline" disabled={Boolean(pending)} onClick={() => void act("revalidate")}>
          {pending === "revalidate" ? "Checking…" : "Check health"}
        </Button>
        <Button size="sm" variant="outline" disabled={Boolean(pending)} onClick={() => void act("toggle")}>
          {pending === "toggle" ? "Saving…" : source.active ? "Disable" : "Enable"}
        </Button>
      </div>
      {message && <p role={message.error ? "alert" : "status"} className={message.error ? "text-xs text-coral" : "text-xs text-muted-foreground"}>{message.text}</p>}
      {history.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs font-bold">Recent collection outcomes</summary>
          <ol className="mt-2 space-y-2 border-l border-border pl-3 text-xs">
            {history.map((run) => (
              <li key={run.runId}>
                {onOpenRun ? (
                  <a href="#run-detail" className="underline" onClick={() => onOpenRun(run.runId)}>
                    {new Date(run.finishedAt).toLocaleString()}
                  </a>
                ) : new Date(run.finishedAt).toLocaleString()}
                {run.status === "FAILED" ? " · Failed" : " · Succeeded"} · {run.jobsSeen} seen · {run.importableStaged} staged as importable
                {run.errorMessage && <p className="break-words text-coral">{run.errorMessage}</p>}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}

export function ScraperSourceHealth({
  sources,
  error,
  refreshing,
  onRefresh,
  onOpenRun,
}: {
  sources: ScrapeSource[] | undefined;
  error?: string;
  refreshing: boolean;
  onRefresh: () => void;
  onOpenRun?: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [onlyAttention, setOnlyAttention] = useState(false);
  const ranked = (sources ?? []).map((source) => {
    const recentFailures = (source.recentRuns ?? []).filter((run) => run.status === "FAILED").length;
    const needsAttention = source.active && (
      source.healthStatus === "FAILING" || source.healthStatus === "COOLDOWN" || recentFailures >= 2
    );
    return { source, recentFailures, needsAttention };
  }).sort((left, right) =>
    Number(right.needsAttention) - Number(left.needsAttention) ||
    right.source.consecutiveFailures - left.source.consecutiveFailures ||
    right.recentFailures - left.recentFailures ||
    left.source.name.localeCompare(right.source.name),
  );
  const term = search.trim().toLowerCase();
  const visible = ranked.filter(({ source, needsAttention }) =>
    (!onlyAttention || needsAttention) &&
    `${source.name} ${source.atsType} ${source.sourceKey}`.toLowerCase().includes(term),
  );

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="ops-label text-purple">Source health</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {sources ? `${sources.filter((source) => source.active).length} active · ${ranked.filter((row) => row.needsAttention).length} need attention` : "Employer boards and recent collection outcomes"}
          </p>
        </div>
        <Button size="sm" variant="outline" disabled={refreshing} onClick={onRefresh}>
          {refreshing ? "Refreshing…" : error ? "Retry inventory" : "Reload inventory"}
        </Button>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-coral">{sources ? "Showing the last loaded inventory. " : ""}{error}</p>}
      {!sources && !error && <p role="status" className="mt-3 text-sm text-muted-foreground">Loading source inventory…</p>}
      {sources?.length === 0 && <p className="mt-3 text-sm text-muted-foreground">No boards in the inventory yet. Add a careers URL or run source discovery.</p>}
      {Boolean(sources?.length) && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Input className="max-w-sm" aria-label="Search employer boards" placeholder="Search employer or ATS" value={search} onChange={(event) => setSearch(event.target.value)} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={onlyAttention} onChange={(event) => setOnlyAttention(event.target.checked)} />
              Needs attention only
            </label>
          </div>
          {visible.length ? (
            <div className="mt-3 max-h-[32rem] divide-y divide-border overflow-auto rounded-lg border border-border">
              {visible.map(({ source }) => <SourceRow key={source.id} source={source} onChange={onRefresh} onOpenRun={onOpenRun} />)}
            </div>
          ) : <p className="mt-3 text-sm text-muted-foreground">No boards match these filters.</p>}
        </>
      )}
    </>
  );
}
