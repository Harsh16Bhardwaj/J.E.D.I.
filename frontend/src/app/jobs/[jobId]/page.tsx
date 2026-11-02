"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowUpRight,
  Bookmark,
  BookmarkCheck,
  BriefcaseBusiness,
  Building2,
  CalendarClock,
  CheckCircle2,
  Clock3,
  MapPin,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { SkillGapButton } from "@/components/skill-gap";
import { BrutalCard } from "@/components/brutal-card";
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
  apiRequest,
  errorSummary,
  isApiError,
  type ApplicationMilestone,
  type ApplicationRecord,
  type JobDetail,
  type JobEvent,
  type JobStateResult,
  type PredictionSummary,
} from "@/lib/api";
import { formatCompensationLpa, postedDaysAgo } from "@/lib/job-display";

const statuses = [
  "NOT_STARTED",
  "PREPARING",
  "APPLIED",
  "SCREENING",
  "ASSESSMENT",
  "INTERVIEW",
  "OFFER",
  "ACCEPTED",
  "REJECTED",
  "WITHDRAWN",
];

const cleanLabel = (value: string) => value.toLowerCase().replaceAll("_", " ");
const localValue = (value: string | null) => (value ? value.slice(0, 16) : "");
const isoValue = (value: string) => (value ? new Date(value).toISOString() : null);
const fallback = (value: string | null | undefined) => value?.trim() || "Not specified";

function RequestError({ error }: { error: unknown }) {
  return (
    <div role="alert" className="rounded-lg border border-coral/40 bg-coral/5 p-4 text-sm text-coral">
      <p>{errorSummary(error)}</p>
      {isApiError(error) && error.requestId ? (
        <p className="mt-2 break-all font-mono text-[11px] text-muted-foreground">Request ID: {error.requestId}</p>
      ) : null}
    </div>
  );
}

function experienceLabel(job: JobDetail["job"]) {
  if (job.experienceMinYears === null && job.experienceMaxYears === null) return "Not specified";
  if (job.experienceMinYears !== null && job.experienceMaxYears !== null) {
    return `${job.experienceMinYears}–${job.experienceMaxYears} years`;
  }
  if (job.experienceMinYears !== null) return `${job.experienceMinYears}+ years`;
  return `Up to ${job.experienceMaxYears} years`;
}

function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleDateString(undefined, { dateStyle: "medium" }) : "Not specified";
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-border py-3 last:border-0">
      <p className="ops-label text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-semibold capitalize">{value}</p>
    </div>
  );
}

function ScorePanel({ predictions }: { predictions: PredictionSummary[] }) {
  const latest = predictions[0];
  if (!latest) {
    return (
      <BrutalCard className="border-dashed text-center">
        <Sparkles className="mx-auto size-6 text-muted-foreground" />
        <p className="mt-3 font-semibold">Not ranked yet</p>
        <p className="mt-1 text-sm text-muted-foreground">This job has no successful model result.</p>
      </BrutalCard>
    );
  }
  const threshold = latest.applyThreshold ?? 0.6;
  const probability = latest.applyPreferenceProbability * 100;
  return (
    <BrutalCard className="border-purple/30 bg-gradient-to-br from-purple/10 via-card to-acid/5">
      <div className="flex items-start justify-between gap-5">
        <div>
          <p className="ops-label text-muted-foreground">Latest model result</p>
          <p className="mt-2 text-sm text-muted-foreground">Persisted rank #{latest.rank}</p>
        </div>
        <span className={`rounded-full border px-3 py-1 text-xs font-bold ${latest.applyRecommendation ? "border-acid/40 bg-acid/10 text-acid" : "border-coral/40 bg-coral/10 text-coral"}`}>
          {latest.applyRecommendation ? "Apply" : "Do not apply"}
        </span>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-border bg-background/70 p-4">
          <p className="ops-label text-muted-foreground">Preference</p>
          <p className="mt-2 text-4xl font-black tracking-[-0.06em]">{latest.rankingScore.toFixed(1)}</p>
        </div>
        <div className="rounded-lg border border-border bg-background/70 p-4">
          <p className="ops-label text-muted-foreground">Apply probability</p>
          <p className={`mt-2 text-3xl font-black ${probability >= threshold * 100 ? "text-acid" : "text-coral"}`}>
            {probability.toFixed(1)}%
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground">Threshold {(threshold * 100).toFixed(0)}%</p>
        </div>
      </div>
      {latest.componentScores ? (
        <details className="mt-4 rounded-lg border border-border bg-background/50 p-3">
          <summary className="cursor-pointer text-xs font-bold uppercase tracking-wide">Predicted fit components</summary>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {Object.entries(latest.componentScores).map(([name, score]) => (
              <div key={name} className="flex justify-between gap-3 rounded-md bg-raised px-3 py-2 text-xs">
                <span className="text-muted-foreground">{cleanLabel(name)}</span>
                <strong>{score.toFixed(2)}</strong>
              </div>
            ))}
          </div>
        </details>
      ) : null}
      {predictions.length > 1 ? (
        <p className="mt-4 text-xs text-muted-foreground">{predictions.length} ranking versions are retained in history.</p>
      ) : null}
    </BrutalCard>
  );
}

function ApplicationPanel({ jobId, application, refresh }: { jobId: string; application: ApplicationRecord; refresh: () => Promise<void> }) {
  const [nextAction, setNextAction] = useState(application.nextAction ?? "");
  const [dueAt, setDueAt] = useState(localValue(application.nextActionDueAt));
  const [targetAt, setTargetAt] = useState(localValue(application.targetApplyBy));
  const [portalUrl, setPortalUrl] = useState(application.portalUrl ?? "");
  const [referenceCode, setReferenceCode] = useState(application.referenceCode ?? "");
  const [notes, setNotes] = useState(application.notes ?? "");
  const [statusOpen, setStatusOpen] = useState(false);
  const [nextStatus, setNextStatus] = useState(application.status);
  const [eventNotes, setEventNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  async function savePlan() {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      await apiRequest(`/api/jobs/${jobId}/application`, {
        method: "PATCH",
        body: JSON.stringify({
          nextAction: nextAction || null,
          nextActionDueAt: isoValue(dueAt),
          targetApplyBy: isoValue(targetAt),
          portalUrl: portalUrl || null,
          referenceCode: referenceCode || null,
          notes: notes || null,
          expectedUpdatedAt: application.updatedAt,
        }),
      });
      toast.success("Your private application plan was saved.");
      await refresh();
    } catch (caught) {
      setError(caught);
      toast.error(errorSummary(caught));
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus() {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      await apiRequest(`/api/jobs/${jobId}/application-events`, {
        method: "POST",
        body: JSON.stringify({ applicationStatus: nextStatus, notes: eventNotes || null }),
      });
      toast.success(`Application moved to ${cleanLabel(nextStatus)}.`);
      setStatusOpen(false);
      setEventNotes("");
      await refresh();
    } catch (caught) {
      setError(caught);
      toast.error(errorSummary(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <BrutalCard className="space-y-5 border-acid/20">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="ops-label text-muted-foreground">Your private application</p>
          <h2 className="mt-2 text-xl font-black uppercase">Plan and progress</h2>
        </div>
        <StatusBadge tone={application.status === "NOT_STARTED" ? "offline" : "queued"}>{cleanLabel(application.status)}</StatusBadge>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1.5 text-xs text-muted-foreground">Next action<Input className="min-h-11" value={nextAction} onChange={(event) => setNextAction(event.target.value)} placeholder="Prepare cover letter" /></label>
        <label className="grid gap-1.5 text-xs text-muted-foreground">Due date<Input type="datetime-local" className="min-h-11" value={dueAt} onChange={(event) => setDueAt(event.target.value)} /></label>
        <label className="grid gap-1.5 text-xs text-muted-foreground">Target apply date<Input type="datetime-local" className="min-h-11" value={targetAt} onChange={(event) => setTargetAt(event.target.value)} /></label>
        <label className="grid gap-1.5 text-xs text-muted-foreground">Reference code<Input className="min-h-11" value={referenceCode} onChange={(event) => setReferenceCode(event.target.value)} /></label>
      </div>
      <label className="grid gap-1.5 text-xs text-muted-foreground">Portal URL<Input className="min-h-11" value={portalUrl} onChange={(event) => setPortalUrl(event.target.value)} /></label>
      <label className="grid gap-1.5 text-xs text-muted-foreground">Application notes<Textarea className="min-h-24" value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
      {error ? <RequestError error={error} /> : null}
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy} onClick={() => void savePlan()}><Save />Save plan</Button>
        <Button variant="outline" disabled={busy} onClick={() => { setNextStatus(application.status); setStatusOpen(true); }}><BriefcaseBusiness />Change stage</Button>
      </div>
      <Dialog open={statusOpen} onOpenChange={(open) => { if (!busy) setStatusOpen(open); }}>
        <DialogContent showCloseButton={!busy}>
          <DialogHeader>
            <DialogTitle className="font-black uppercase">Record status change</DialogTitle>
            <DialogDescription>This changes only your private application and adds a permanent history event.</DialogDescription>
          </DialogHeader>
          <select className="min-h-11 rounded-lg border bg-background px-3" value={nextStatus} onChange={(event) => setNextStatus(event.target.value)}>
            {statuses.map((value) => <option key={value}>{value}</option>)}
          </select>
          <Textarea placeholder="Optional context" value={eventNotes} onChange={(event) => setEventNotes(event.target.value)} />
          {error ? <RequestError error={error} /> : null}
          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setStatusOpen(false)}>Cancel</Button>
            <Button disabled={busy} onClick={() => void changeStatus()}>{busy ? "Saving..." : "Record change"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </BrutalCard>
  );
}

function Milestones({ jobId, items, refresh }: { jobId: string; items: ApplicationMilestone[]; refresh: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [type, setType] = useState("INTERVIEW");
  const [scheduledAt, setScheduledAt] = useState("");
  const [busy, setBusy] = useState(false);

  async function create() {
    if (!title.trim() || busy) return;
    setBusy(true);
    try {
      await apiRequest(`/api/jobs/${jobId}/application-milestones`, {
        method: "POST",
        body: JSON.stringify({ type, title, scheduledAt: isoValue(scheduledAt) }),
      });
      toast.success("Private milestone added.");
      setOpen(false);
      setTitle("");
      await refresh();
    } catch (error) {
      toast.error(errorSummary(error));
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(item: ApplicationMilestone, status: string) {
    if (busy) return;
    setBusy(true);
    try {
      await apiRequest(`/api/jobs/${jobId}/application-milestones/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      toast.success("Milestone updated.");
      await refresh();
    } catch (error) {
      toast.error(errorSummary(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <BrutalCard>
      <div className="flex items-start justify-between gap-4">
        <div><p className="ops-label text-muted-foreground">Application rounds</p><h2 className="mt-2 text-xl font-black uppercase">Milestones</h2></div>
        <Button variant="outline" onClick={() => setOpen(true)}><Plus />Add</Button>
      </div>
      <div className="mt-5 space-y-2">
        {items.length ? items.map((item) => (
          <div key={item.id} className="flex flex-col gap-3 rounded-lg border bg-raised/40 p-4 sm:flex-row sm:items-center">
            <div className="flex-1"><p className="font-bold">{item.title}</p><p className="mt-1 text-xs text-muted-foreground">{cleanLabel(item.type)} · {item.scheduledAt ? new Date(item.scheduledAt).toLocaleString() : "Unscheduled"}</p></div>
            <StatusBadge tone={item.status === "COMPLETED" ? "ready" : item.status === "CANCELLED" ? "warning" : "queued"}>{item.status}</StatusBadge>
            <select disabled={busy} className="min-h-10 rounded-lg border bg-background px-2 text-xs" value={item.status} onChange={(event) => void setStatus(item, event.target.value)}>
              {["PLANNED", "COMPLETED", "CANCELLED"].map((value) => <option key={value}>{value}</option>)}
            </select>
          </div>
        )) : <p className="py-8 text-center text-sm text-muted-foreground">No screening, assessment, or interview rounds recorded.</p>}
      </div>
      <Dialog open={open} onOpenChange={(value) => { if (!busy) setOpen(value); }}>
        <DialogContent showCloseButton={!busy}>
          <DialogHeader><DialogTitle className="font-black uppercase">Add milestone</DialogTitle><DialogDescription>Record a company-specific round without changing the main application stage.</DialogDescription></DialogHeader>
          <Input placeholder="Technical Round 2" value={title} onChange={(event) => setTitle(event.target.value)} />
          <select className="min-h-11 rounded-lg border bg-background px-3" value={type} onChange={(event) => setType(event.target.value)}>
            {["SCREENING", "ASSESSMENT", "INTERVIEW", "FOLLOW_UP", "OTHER"].map((value) => <option key={value}>{value}</option>)}
          </select>
          <Input type="datetime-local" className="min-h-11" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} />
          <DialogFooter><Button variant="outline" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button><Button disabled={busy || !title.trim()} onClick={() => void create()}>{busy ? "Adding..." : "Add milestone"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </BrutalCard>
  );
}

export default function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const detailKey = `/api/jobs/${jobId}`;
  const detail = useSWR<JobDetail>(detailKey);
  const { mutate: mutateGlobal } = useSWRConfig();
  const viewed = useRef(false);
  const [bookmarking, setBookmarking] = useState(false);

  useEffect(() => {
    if (!detail.data || viewed.current) return;
    viewed.current = true;
    void apiRequest<JobStateResult>(`/api/jobs/${jobId}/view`, { method: "POST" })
      .then(async (state) => {
        await detail.mutate((current) => (current ? { ...current, state } : current), { revalidate: false });
        await mutateGlobal(
          (key) => typeof key === "string" && (key.startsWith("/api/jobs?") || key.startsWith("/api/dashboard")),
          undefined,
          { revalidate: true },
        );
      })
      .catch(() => undefined);
  }, [detail, jobId, mutateGlobal]);

  async function refresh() {
    await Promise.all([
      detail.mutate(),
      mutateGlobal(
        (key) => typeof key === "string" && (key.startsWith("/api/jobs?") || key.startsWith("/api/applications") || key.startsWith("/api/dashboard")),
        undefined,
        { revalidate: true },
      ),
    ]);
  }

  async function toggleBookmark() {
    if (!detail.data || bookmarking) return;
    setBookmarking(true);
    const bookmarked = detail.data.state?.reviewStatus === "SAVED";
    try {
      const state = await apiRequest<JobStateResult>(`/api/jobs/${jobId}/state`, {
        method: "PATCH",
        body: JSON.stringify({ reviewStatus: bookmarked ? "VIEWED" : "SAVED" }),
      });
      await detail.mutate((current) => (current ? { ...current, state } : current), { revalidate: false });
      await mutateGlobal(
        (key) => typeof key === "string" && (key.startsWith("/api/jobs?") || key.startsWith("/api/dashboard")),
        undefined,
        { revalidate: true },
      );
      toast.success(bookmarked ? "Bookmark removed." : "Job bookmarked.");
    } catch (error) {
      toast.error(errorSummary(error));
    } finally {
      setBookmarking(false);
    }
  }

  if (detail.isLoading) {
    return <div className="space-y-4"><Skeleton className="h-52 rounded-xl bg-raised" /><Skeleton className="h-[60vh] rounded-xl bg-raised" /></div>;
  }
  if (detail.error || !detail.data) {
    return <BrutalCard className="border-coral/40"><p className="ops-label text-coral">Job detail unavailable</p><RequestError error={detail.error} /><Button className="mt-5" onClick={() => void detail.mutate()}><RefreshCw />Retry</Button></BrutalCard>;
  }

  const data = detail.data;
  const bookmarked = data.state?.reviewStatus === "SAVED";
  const timeline: Array<{ id: string; title: string; at: string; detail: string }> = [
    ...data.events.map((event: JobEvent) => ({
      id: event.id,
      title: cleanLabel(event.newStatus ?? event.eventType),
      at: event.eventAt,
      detail: event.notes ?? `Moved from ${cleanLabel(event.previousStatus ?? "not started")}`,
    })),
    ...data.milestones.map((item) => ({
      id: item.id,
      title: item.title,
      at: item.completedAt ?? item.scheduledAt ?? item.createdAt,
      detail: `${cleanLabel(item.type)} · ${cleanLabel(item.status)}`,
    })),
  ].sort((a, b) => +new Date(b.at) - +new Date(a.at));

  return (
    <div className="space-y-8">
      <Link href="/jobs" className="inline-flex items-center gap-2 text-xs text-muted-foreground hover:text-acid"><ArrowLeft className="size-4" />Back to jobs</Link>

      <header className="relative overflow-hidden rounded-xl border border-purple/30 bg-gradient-to-br from-purple/15 via-card to-acid/10 p-6 sm:p-8">
        <div className="absolute -right-16 -top-20 size-64 rounded-full bg-purple/10 blur-3xl" />
        <div className="relative flex flex-col justify-between gap-6 lg:flex-row lg:items-start">
          <div className="flex min-w-0 gap-4">
            <div className="grid size-14 shrink-0 place-items-center rounded-xl border-2 border-purple/40 bg-purple/10 text-2xl font-black text-purple">{data.job.companyName.trim().charAt(0).toUpperCase() || "J"}</div>
            <div className="min-w-0">
              <p className="font-semibold text-purple">{data.job.companyName}</p>
              <h1 className="mt-2 max-w-4xl text-3xl font-black uppercase leading-tight tracking-[-0.04em] sm:text-5xl">{data.job.roleTitle}</h1>
              <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1.5"><MapPin className="size-3.5" />{fallback(data.job.location)}</span>
                <span>·</span><span className="capitalize">{fallback(data.job.employmentType)}</span>
                <span>·</span><span className="capitalize">{fallback(data.job.workMode)}</span>
              </div>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <SkillGapButton jobId={data.job.id} />
            <Button aria-pressed={bookmarked} variant="outline" disabled={bookmarking} className={bookmarked ? "border-purple bg-purple/15 text-purple" : ""} onClick={() => void toggleBookmark()}>
              {bookmarked ? <BookmarkCheck /> : <Bookmark />}{bookmarked ? "Bookmarked" : "Bookmark"}
            </Button>
            <a href={data.job.applyUrl} target="_blank" rel="noreferrer" className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-foreground px-4 text-sm font-bold text-background transition hover:bg-acid">
              Open application <ArrowUpRight className="size-4" />
            </a>
          </div>
        </div>
      </header>

      <section className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Salary", formatCompensationLpa(data.job)],
          ["Experience", experienceLabel(data.job)],
          ["Posted", postedDaysAgo(data.batch.createdAt)],
          ["Deadline", dateLabel(data.job.applicationDeadline)],
        ].map(([label, value]) => <div key={label} className="bg-card p-5"><p className="ops-label text-muted-foreground">{label}</p><p className="mt-2 font-bold">{value}</p></div>)}
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(20rem,.65fr)]">
        <div className="space-y-6">
          <BrutalCard>
            <div className="flex items-center gap-2"><Building2 className="size-4 text-purple" /><p className="ops-label text-muted-foreground">Job description</p></div>
            <div className="mt-5 whitespace-pre-wrap text-sm leading-7 text-foreground/85">{data.job.description?.trim() || "The source did not provide a job description."}</div>
            <div className="mt-7 border-t border-border pt-5">
              <p className="ops-label text-muted-foreground">Skills</p>
              {data.job.skills.length ? <div className="mt-3 flex flex-wrap gap-2">{data.job.skills.map((skill) => <span key={skill} className="rounded-full border border-purple/25 bg-purple/5 px-3 py-1.5 text-xs font-medium">{skill}</span>)}</div> : <p className="mt-2 text-sm text-muted-foreground">No explicit skills were listed.</p>}
            </div>
          </BrutalCard>
          <ApplicationPanel key={data.application.updatedAt ?? "new"} jobId={jobId} application={data.application} refresh={refresh} />
        </div>

        <aside className="space-y-6 xl:sticky xl:top-6">
          <ScorePanel predictions={data.predictions} />
          <BrutalCard>
            <p className="ops-label text-muted-foreground">Job facts</p>
            <div className="mt-3">
              <Fact label="Role family" value={fallback(data.job.roleFamily)} />
              <Fact label="Seniority" value={fallback(data.job.seniority)} />
              <Fact label="Experience" value={experienceLabel(data.job)} />
              <Fact label="Work mode" value={fallback(data.job.workMode)} />
              <Fact label="Employment type" value={fallback(data.job.employmentType)} />
              <Fact label="Location" value={fallback(data.job.location)} />
              <Fact label="Salary" value={formatCompensationLpa(data.job)} />
              <Fact label="Can apply now" value={data.job.canApplyNow === null ? "Unknown" : data.job.canApplyNow ? "Yes" : "No"} />
            </div>
          </BrutalCard>
        </aside>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Milestones jobId={jobId} items={data.milestones} refresh={refresh} />
        <BrutalCard>
          <div className="flex items-center gap-2"><CalendarClock className="size-4 text-purple" /><div><p className="ops-label text-muted-foreground">Private history</p><h2 className="mt-2 text-xl font-black uppercase">Application timeline</h2></div></div>
          <div className="mt-5 space-y-4">
            {timeline.length ? timeline.map((item) => <div key={item.id} className="relative border-l border-border pl-5"><CheckCircle2 className="absolute -left-2 top-0 size-4 bg-card text-acid" /><p className="font-bold capitalize">{item.title}</p><p className="mt-1 text-xs text-muted-foreground">{item.detail}</p><p className="mt-1 flex items-center gap-1 font-mono text-[10px] text-muted-foreground"><Clock3 className="size-3" />{new Date(item.at).toLocaleString()}</p></div>) : <p className="py-8 text-center text-sm text-muted-foreground">No private application activity yet.</p>}
          </div>
        </BrutalCard>
      </div>
    </div>
  );
}
