"use client";

import { FormEvent, Suspense, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CalendarClock,
  ChevronRight,
  LockKeyhole,
  RefreshCw,
  Search,
} from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { PrivateDraftApplications } from "@/components/private-draft-applications";
import { StatusBadge } from "@/components/status-badge";
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
import { Textarea } from "@/components/ui/textarea";
import {
  needsApplicationCorrection,
  prepareApplicationMove,
  type ApplicationMoveAttempt,
} from "@/lib/application-move";
import {
  apiRequest,
  errorSummary,
  type ApplicationListItem,
  type ApplicationPage,
} from "@/lib/api";

const PAGE_SIZE = 100;
const stages = [
  { title: "Preparing", statuses: ["PREPARING"] },
  { title: "Applied", statuses: ["APPLIED"] },
  { title: "Screening", statuses: ["SCREENING"] },
  { title: "Assessment", statuses: ["ASSESSMENT"] },
  { title: "Interview", statuses: ["INTERVIEW"] },
  { title: "Offer", statuses: ["OFFER"] },
  { title: "Outcome", statuses: ["ACCEPTED", "REJECTED", "WITHDRAWN"] },
];
const allStatuses = [
  "NOT_STARTED",
  ...stages.flatMap((stage) => stage.statuses),
];
const label = (value: string) => value.toLowerCase().replaceAll("_", " ");

function dueTone(value: string | null) {
  if (!value) return null;
  const due = new Date(value);
  const now = new Date();
  if (due < now) return { text: "Overdue", className: "text-coral" };
  if (due.toDateString() === now.toDateString())
    return { text: "Due today", className: "text-acid" };
  return { text: due.toLocaleDateString(), className: "text-muted-foreground" };
}

function ApplicationCard({
  item,
  onMove,
}: {
  item: ApplicationListItem;
  onMove: () => void;
}) {
  const due = dueTone(item.application.nextActionDueAt);
  return (
    <article className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <StatusBadge
          tone={
            item.application.status === "REJECTED" ||
            item.application.status === "WITHDRAWN"
              ? "warning"
              : "queued"
          }
        >
          {label(item.application.status)}
        </StatusBadge>
        {item.job.latestPrediction && (
          <span className="font-mono text-xs text-muted-foreground">
            #{item.job.latestPrediction.rank} ·{" "}
            {item.job.latestPrediction.rankingScore.toFixed(1)}
          </span>
        )}
      </div>
      <Link
        href={`/jobs/${item.job.id}`}
        className="mt-4 block hover:text-acid"
      >
        <h3 className="break-words text-base font-semibold leading-snug">
          {item.job.roleTitle}
        </h3>
        <p className="mt-1 text-xs text-muted-foreground">
          {item.job.companyName}
        </p>
      </Link>
      <div className="mt-3 border-t border-border pt-3">
        <p className="text-xs font-bold">
          {item.application.nextAction ?? "No next action"}
        </p>
        {due && <p className={`ops-label mt-1 ${due.className}`}>{due.text}</p>}
      </div>
      <div className="mt-4 flex items-center justify-between">
        <p className="text-[10px] text-muted-foreground">
          {item.latestEvent
            ? new Date(item.latestEvent.eventAt).toLocaleDateString()
            : "No history"}
        </p>
        <Button size="sm" variant="ghost" onClick={onMove}>
          Move <ChevronRight />
        </Button>
      </div>
    </article>
  );
}

function ApplicationsWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { mutate: mutateGlobal } = useSWRConfig();
  const [selected, setSelected] = useState<ApplicationListItem>();
  const [nextStatus, setNextStatus] = useState("APPLIED");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const attempt = useRef<ApplicationMoveAttempt>(undefined);
  const searchForm = useRef<HTMLFormElement>(null);
  const correcting = Boolean(
    selected &&
      needsApplicationCorrection(selected.application.status, nextStatus),
  );
  const canMove =
    selected &&
    selected.application.status !== nextStatus &&
    (!correcting || notes.trim());
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);
  const query = useMemo(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(page));
    params.set("pageSize", String(PAGE_SIZE));
    return params.toString();
  }, [page, searchParams]);
  const applications = useSWR<ApplicationPage>(`/api/applications?${query}`);
  const activeStatus = searchParams.get("applicationStatus") ?? "";
  const urlSearch = searchParams.get("search") ?? "";
  const visibleStages = activeStatus
    ? [{ title: label(activeStatus), statuses: [activeStatus] }]
    : stages;
  const hasFilters = Boolean(
    urlSearch ||
      activeStatus ||
      (searchParams.get("due") && searchParams.get("due") !== "all"),
  );
  const populatedStages = visibleStages.filter((stage) =>
    applications.data?.items.some((item) =>
      stage.statuses.includes(item.application.status),
    ),
  );
  const pages = Math.max(
    1,
    Math.ceil((applications.data?.total ?? 0) / PAGE_SIZE),
  );
  function update(values: Record<string, string | number>) {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(values).forEach(([key, value]) =>
      value === "" ? params.delete(key) : params.set(key, String(value)),
    );
    router.replace(`${pathname}?${params}`, { scroll: false });
  }
  function clearFilters() {
    searchForm.current?.reset();
    router.replace(pathname, { scroll: false });
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("search");
    update({ search: String(value ?? "").trim(), page: 1 });
  }
  function openMove(item: ApplicationListItem) {
    attempt.current = undefined;
    setSelected(item);
    setNextStatus(item.application.status);
    setNotes("");
    setError(undefined);
  }
  async function move() {
    if (!selected || !canMove || busy) return;
    setBusy(true);
    setError(undefined);
    const request = prepareApplicationMove(
      selected.application,
      nextStatus,
      notes,
      attempt.current,
    );
    attempt.current = request.attempt;
    try {
      await apiRequest(`/api/jobs/${selected.job.id}/application-events`, {
        method: "POST",
        body: request.body,
        signal: AbortSignal.timeout(15_000),
      });
      toast.success(`Your application moved to ${label(nextStatus)}.`);
      setSelected(undefined);
      void mutateGlobal(
        (key) =>
          typeof key === "string" &&
          (key.startsWith("/api/applications") ||
            key.startsWith("/api/jobs") ||
            key.startsWith("/api/dashboard")),
        undefined,
        { revalidate: true },
      );
    } catch (caught) {
      setError(errorSummary(caught));
      void applications.mutate();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border pb-5">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Applications
          </h1>
          <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <LockKeyhole className="size-3" aria-hidden="true" />
            Only visible to you
          </p>
        </div>
        <Link
          href="/jobs"
          className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-border px-3 text-sm hover:bg-muted"
        >
          Browse jobs <ArrowUpRight className="size-4" />
        </Link>
      </header>

      <section
        aria-label="Application filters"
        className="space-y-3 rounded-xl border border-border bg-card p-3 sm:p-4"
      >
        <form ref={searchForm} onSubmit={submit} className="flex gap-2">
          <div className="relative min-w-0 flex-1">
            <Search
              className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              aria-label="Search applications"
              className="min-h-10 pl-9"
              name="search"
              key={urlSearch}
              defaultValue={urlSearch}
              placeholder="Search company or role"
            />
          </div>
          <Button type="submit" className="min-h-10">
            Search
          </Button>
        </form>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-end">
          <label className="grid gap-1.5 text-xs text-muted-foreground">
            Stage
            <select
              className="min-h-10 rounded-lg border border-border bg-background px-2 text-sm capitalize text-foreground"
              aria-label="Stage"
              value={activeStatus}
              onChange={(event) =>
                update({ applicationStatus: event.target.value, page: 1 })
              }
            >
              <option value="">Active stages</option>
              {allStatuses.map((status) => (
                <option key={status} value={status}>
                  {label(status)}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1.5 text-xs text-muted-foreground">
            Due
            <select
              className="min-h-10 rounded-lg border border-border bg-background px-2 text-sm text-foreground"
              aria-label="Due"
              value={searchParams.get("due") ?? "all"}
              onChange={(event) => update({ due: event.target.value, page: 1 })}
            >
              {[
                ["all", "Any date"],
                ["overdue", "Overdue"],
                ["today", "Today"],
                ["week", "This week"],
                ["none", "No deadline"],
              ].map(([value, title]) => (
                <option key={value} value={value}>
                  {title}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1.5 text-xs text-muted-foreground">
            Sort
            <select
              className="min-h-10 rounded-lg border border-border bg-background px-2 text-sm text-foreground"
              aria-label="Sort"
              value={searchParams.get("sort") ?? "updated"}
              onChange={(event) =>
                update({ sort: event.target.value, page: 1 })
              }
            >
              <option value="updated">Recently updated</option>
              <option value="nextAction">Next action</option>
            </select>
          </label>
          {hasFilters && (
            <Button variant="ghost" className="min-h-10" onClick={clearFilters}>
              Clear filters
            </Button>
          )}
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <p aria-live="polite">
          {applications.data
            ? `${applications.data.total} matching applications`
            : "Loading applications…"}
          {applications.data?.overdueCount ? (
            <span className="ml-3 text-coral">
              {applications.data.overdueCount} overdue
            </span>
          ) : null}
        </p>
        {applications.data && applications.data.total > PAGE_SIZE && (
          <span>Stage counts reflect this page</span>
        )}
        {applications.isValidating && !applications.isLoading && (
          <span role="status">Updating…</span>
        )}
      </div>

      {applications.isLoading ? (
        <div role="status" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <span className="sr-only">Loading applications</span>
          {[0, 1, 2].map((item) => (
            <Skeleton key={item} className="h-48 rounded-xl bg-raised" />
          ))}
        </div>
      ) : applications.error ? (
        <BrutalCard className="border-coral/40">
          <p role="alert" className="text-sm text-coral">
            {errorSummary(applications.error)}
          </p>
          <Button className="mt-4" onClick={() => void applications.mutate()}>
            <RefreshCw />
            Retry
          </Button>
        </BrutalCard>
      ) : applications.data?.items.length ? (
        <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
          {populatedStages.map((stage) => {
            const items = applications.data!.items.filter((item) =>
              stage.statuses.includes(item.application.status),
            );
            return (
              <section
                key={stage.title}
                aria-label={stage.title}
                className="min-w-0 rounded-xl border border-border bg-muted/20 p-3"
              >
                <div className="mb-3 flex items-center justify-between px-1">
                  <h2 className="text-sm font-semibold capitalize">
                    {stage.title}
                  </h2>
                  <span className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {items.length}
                  </span>
                </div>
                <div className="space-y-3">
                  {items.map((item) => (
                    <ApplicationCard
                      key={item.job.id}
                      item={item}
                      onMove={() => openMove(item)}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <BrutalCard className="py-12 text-center">
          <CalendarClock
            className="mx-auto size-6 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="mt-4 text-xl font-semibold">
            {hasFilters ? "No matching applications" : "Your pipeline is empty"}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {hasFilters
              ? "Try another search or clear your filters."
              : "Start with a job you want to apply for."}
          </p>
          {hasFilters ? (
            <Button variant="outline" className="mt-5" onClick={clearFilters}>
              Clear filters
            </Button>
          ) : (
            <Button className="mt-5" render={<Link href="/jobs" />}>
              Browse jobs <ArrowUpRight />
            </Button>
          )}
        </BrutalCard>
      )}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          disabled={page <= 1}
          onClick={() => update({ page: page - 1 })}
        >
          <ArrowLeft />
          Previous
        </Button>
        <p className="ops-label text-muted-foreground">
          Page {page} / {pages}
        </p>
        <Button
          variant="outline"
          disabled={page >= pages}
          onClick={() => update({ page: page + 1 })}
        >
          Next
          <ArrowRight />
        </Button>
      </div>
      <PrivateDraftApplications />
      <Dialog
        open={Boolean(selected)}
        onOpenChange={(open) => {
          if (!open && !busy) setSelected(undefined);
        }}
      >
        <DialogContent showCloseButton={!busy}>
          <DialogHeader>
            <DialogTitle className="font-semibold">
              Move application
            </DialogTitle>
            <DialogDescription>
              This records a private status event for {selected?.job.roleTitle}.
            </DialogDescription>
          </DialogHeader>
          <select
            aria-label="New stage"
            disabled={busy}
            className="min-h-11 rounded-lg border bg-background px-3 capitalize"
            value={nextStatus}
            onChange={(event) => setNextStatus(event.target.value)}
          >
            {allStatuses.map((status) => (
              <option key={status} value={status}>
                {label(status)}
              </option>
            ))}
          </select>
          <Textarea
            aria-label={correcting ? "Reason for correction" : "Notes"}
            disabled={busy}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder={
              correcting ? "Reason for the correction" : "Optional context"
            }
          />
          {error && (
            <p role="alert" className="text-sm text-coral">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setSelected(undefined)}
            >
              Cancel
            </Button>
            <Button disabled={busy || !canMove} onClick={() => void move()}>
              {busy
                ? "Saving…"
                : correcting
                  ? "Record correction"
                  : "Record move"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function ApplicationsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[70vh] rounded-xl bg-raised" />}>
      <ApplicationsWorkspace />
    </Suspense>
  );
}
