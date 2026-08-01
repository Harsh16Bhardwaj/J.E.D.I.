"use client";

import { FormEvent, Suspense, useMemo, useState } from "react";
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
import { RouteHeader } from "@/components/route-header";
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
const allStatuses = ["NOT_STARTED", ...stages.flatMap((stage) => stage.statuses)];
const label = (value: string) => value.toLowerCase().replaceAll("_", " ");

function dueTone(value: string | null) {
  if (!value) return null;
  const due = new Date(value);
  const now = new Date();
  if (due < now) return { text: "Overdue", className: "text-coral" };
  if (due.toDateString() === now.toDateString()) return { text: "Due today", className: "text-acid" };
  return { text: due.toLocaleDateString(), className: "text-muted-foreground" };
}

function ApplicationCard({ item, onMove }: { item: ApplicationListItem; onMove: () => void }) {
  const due = dueTone(item.application.nextActionDueAt);
  return <article className="rounded-xl border border-border bg-card p-4">
    <div className="flex items-start justify-between gap-3"><StatusBadge tone={item.application.status === "REJECTED" || item.application.status === "WITHDRAWN" ? "warning" : "queued"}>{label(item.application.status)}</StatusBadge>{item.job.latestPrediction && <span className="font-mono text-xs text-muted-foreground">#{item.job.latestPrediction.rank} · {item.job.latestPrediction.rankingScore.toFixed(1)}</span>}</div>
    <Link href={`/jobs/${item.job.id}`} className="mt-4 block hover:text-acid"><h3 className="font-black uppercase leading-tight">{item.job.roleTitle}</h3><p className="mt-1 text-xs text-muted-foreground">{item.job.companyName}</p></Link>
    <div className="mt-5 min-h-14 border-t border-border pt-3"><p className="text-xs font-bold">{item.application.nextAction ?? "No next action planned"}</p>{due && <p className={`ops-label mt-1 ${due.className}`}>{due.text}</p>}</div>
    <div className="mt-4 flex items-center justify-between"><p className="text-[10px] text-muted-foreground">{item.latestEvent ? new Date(item.latestEvent.eventAt).toLocaleDateString() : "No history"}</p><Button size="sm" variant="ghost" onClick={onMove}>Move <ChevronRight /></Button></div>
  </article>;
}

function ApplicationsWorkspace() {
  const router = useRouter(); const pathname = usePathname(); const searchParams = useSearchParams(); const { mutate: mutateGlobal } = useSWRConfig();
  const [search, setSearch] = useState(searchParams.get("search") ?? "");
  const [selected, setSelected] = useState<ApplicationListItem>();
  const [nextStatus, setNextStatus] = useState("APPLIED");
  const [notes, setNotes] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState<string>();
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);
  const query = useMemo(() => { const params = new URLSearchParams(searchParams.toString()); params.set("page", String(page)); params.set("pageSize", String(PAGE_SIZE)); return params.toString(); }, [page, searchParams]);
  const applications = useSWR<ApplicationPage>(`/api/applications?${query}`);
  const pages = Math.max(1, Math.ceil((applications.data?.total ?? 0) / PAGE_SIZE));
  function update(values: Record<string, string | number>) { const params = new URLSearchParams(searchParams.toString()); Object.entries(values).forEach(([key, value]) => value === "" ? params.delete(key) : params.set(key, String(value))); router.replace(`${pathname}?${params}`, { scroll: false }); }
  function submit(event: FormEvent) { event.preventDefault(); update({ search: search.trim(), page: 1 }); }
  async function move() { if (!selected || busy) return; setBusy(true); setError(undefined); try { await apiRequest(`/api/jobs/${selected.job.id}/application-events`, { method: "POST", body: JSON.stringify({ applicationStatus: nextStatus, notes: notes || null }) }); toast.success(`Your application moved to ${label(nextStatus)}.`); await mutateGlobal((key) => typeof key === "string" && (key.startsWith("/api/applications") || key.startsWith("/api/jobs") || key.startsWith("/api/dashboard")), undefined, { revalidate: true }); setSelected(undefined); setNotes(""); } catch (caught) { setError(errorSummary(caught)); toast.error(errorSummary(caught)); } finally { setBusy(false); } }
  return <div className="space-y-8"><RouteHeader eyebrow="Private pipeline" title="Your application command board" path="/applications" description="Jobs and rankings are shared with the group. Every stage, deadline, note and interview round shown here belongs only to your account." />
    <div className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground"><LockKeyhole className="size-4 shrink-0" />Other group members cannot see or change this pipeline.</div>
    <section className="grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-3">{[["Active", applications.data?.total ?? "—"], ["Overdue", applications.data?.overdueCount ?? "—"], ["Next action", searchParams.get("due") ? label(searchParams.get("due")!) : "All dates"]].map(([name, value]) => <div key={name as string} className="bg-card p-5"><p className="ops-label text-muted-foreground">{name as string}</p><p className="mt-2 text-2xl font-black uppercase">{value as string}</p></div>)}</section>
    <BrutalCard><form onSubmit={submit} className="flex gap-2"><div className="relative flex-1"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input className="min-h-11 pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search company or role" /></div><Button type="submit">Search</Button></form><div className="mt-4 grid gap-3 sm:grid-cols-3"><label className="grid gap-1 text-xs text-muted-foreground">Status<select className="min-h-11 rounded-lg border bg-background px-3" value={searchParams.get("applicationStatus") ?? ""} onChange={(event) => update({ applicationStatus: event.target.value, page: 1 })}><option value="">Active stages</option>{allStatuses.map((status) => <option key={status}>{status}</option>)}</select></label><label className="grid gap-1 text-xs text-muted-foreground">Due<select className="min-h-11 rounded-lg border bg-background px-3" value={searchParams.get("due") ?? "all"} onChange={(event) => update({ due: event.target.value, page: 1 })}>{["all", "overdue", "today", "week", "none"].map((value) => <option key={value}>{value}</option>)}</select></label><label className="grid gap-1 text-xs text-muted-foreground">Sort<select className="min-h-11 rounded-lg border bg-background px-3" value={searchParams.get("sort") ?? "updated"} onChange={(event) => update({ sort: event.target.value, page: 1 })}><option value="updated">Recently updated</option><option value="nextAction">Next action</option></select></label></div></BrutalCard>
    {applications.isLoading ? <div className="flex gap-4 overflow-hidden">{[0,1,2].map((item) => <Skeleton key={item} className="h-80 w-72 shrink-0 rounded-xl bg-raised" />)}</div> : applications.error ? <BrutalCard className="border-coral/40"><p className="text-sm text-coral">{errorSummary(applications.error)}</p><Button className="mt-4" onClick={() => void applications.mutate()}><RefreshCw />Retry</Button></BrutalCard> : applications.data?.items.length ? <div className="overflow-x-auto pb-4"><div className="grid min-w-[1540px] grid-cols-7 gap-3">{stages.map((stage) => { const items = applications.data!.items.filter((item) => stage.statuses.includes(item.application.status)); return <section key={stage.title}><div className="mb-3 flex items-center justify-between border-b border-border pb-3"><h2 className="ops-label">{stage.title}</h2><span className="font-mono text-xs text-muted-foreground">{items.length}</span></div><div className="space-y-3">{items.map((item) => <ApplicationCard key={item.job.id} item={item} onMove={() => { setSelected(item); setNextStatus(item.application.status); setError(undefined); }} />)}{!items.length && <div className="rounded-xl border border-dashed border-border p-5 text-center text-xs text-muted-foreground">No applications</div>}</div></section>; })}</div></div> : <BrutalCard className="py-16 text-center"><CalendarClock className="mx-auto size-8 text-muted-foreground" /><h2 className="mt-5 text-2xl font-black uppercase">Your pipeline is empty</h2><p className="mt-2 text-sm text-muted-foreground">Start an application from the ranked jobs queue.</p><Button className="mt-5" render={<Link href="/jobs" />}>Review jobs <ArrowUpRight /></Button></BrutalCard>}
    <div className="flex items-center justify-between"><Button variant="outline" disabled={page <= 1} onClick={() => update({ page: page - 1 })}><ArrowLeft />Previous</Button><p className="ops-label text-muted-foreground">Page {page} / {pages}</p><Button variant="outline" disabled={page >= pages} onClick={() => update({ page: page + 1 })}>Next<ArrowRight /></Button></div>
    <Dialog open={Boolean(selected)} onOpenChange={(open) => { if (!open && !busy) setSelected(undefined); }}><DialogContent showCloseButton={!busy}><DialogHeader><DialogTitle className="font-black uppercase">Move application</DialogTitle><DialogDescription>This records a private status event for {selected?.job.roleTitle}.</DialogDescription></DialogHeader><select className="min-h-11 rounded-lg border bg-background px-3" value={nextStatus} onChange={(event) => setNextStatus(event.target.value)}>{allStatuses.map((status) => <option key={status}>{status}</option>)}</select><Textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional context" />{error && <p className="text-sm text-coral">{error}</p>}<DialogFooter><Button variant="outline" disabled={busy} onClick={() => setSelected(undefined)}>Cancel</Button><Button disabled={busy} onClick={() => void move()}>{busy ? "Saving…" : "Record move"}</Button></DialogFooter></DialogContent></Dialog>
  </div>;
}

export default function ApplicationsPage() { return <Suspense fallback={<Skeleton className="h-[70vh] rounded-xl bg-raised" />}><ApplicationsWorkspace /></Suspense>; }
