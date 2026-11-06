"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import useSWR from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, errorSummary } from "@/lib/api";
import {
  applicationMoveRequest,
  applicationStages,
  needsApplicationCorrection,
  type ApplicationMoveAttempt,
} from "@/lib/application-move";

type DraftApplication = {
  status: string;
  revision: number;
  events: {
    requestId: string;
    fromStatus: string;
    toStatus: string;
    correction: boolean;
    notes: string | null;
    createdAt: string;
  }[];
};

type DraftApplicationItem = {
  draftId: string;
  title: string;
  employer: string;
  application: DraftApplication;
};

const label = (status: string) => status.toLowerCase().replaceAll("_", " ");

function DraftCard({ item, onSaved, refresh }: {
  item: DraftApplicationItem;
  onSaved: (application: DraftApplication) => void;
  refresh: () => void;
}) {
  const [snapshot, setSnapshot] = useState<DraftApplication>();
  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const attempt = useRef<ApplicationMoveAttempt>(undefined);
  const correction = Boolean(snapshot && needsApplicationCorrection(snapshot.status, status));

  function open() {
    setSnapshot(item.application);
    setStatus(item.application.status);
    setNotes("");
    setError(undefined);
    attempt.current = undefined;
  }

  async function move() {
    if (!snapshot || busy || snapshot.status === status || (correction && !notes.trim())) return;
    setBusy(true);
    setError(undefined);
    const request = applicationMoveRequest({
      status, expectedRevision: snapshot.revision, notes: notes.trim() || null, correction,
    }, attempt.current);
    attempt.current = request.attempt;
    try {
      const application = await apiRequest<DraftApplication>(`/api/job-drafts/${item.draftId}/application`, {
        method: "PATCH",
        body: request.body,
        signal: AbortSignal.timeout(15_000),
      });
      onSaved(application);
      setSnapshot(undefined);
    } catch (caught) {
      setError(errorSummary(caught));
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="min-w-0 space-y-3 rounded-xl border border-border bg-card p-4">
      <p className="ops-label">{label(item.application.status)}</p>
      <Link href={`/jobs/intake?draft=${item.draftId}`} className="block break-words hover:text-acid">
        <h3 className="font-bold">{item.title || "Untitled job"}</h3>
        {item.employer && <p className="text-sm text-muted-foreground">{item.employer}</p>}
      </Link>
      {snapshot ? (
        <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); void move(); }}>
          <label className="grid gap-1 text-sm">
            New stage
            <select disabled={busy} className="min-h-10 rounded-lg border bg-background px-2 capitalize" value={status} onChange={(event) => setStatus(event.target.value)}>
              {applicationStages.map((stage) => <option key={stage} value={stage}>{label(stage)}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            {correction ? "Reason for correction" : "Notes (optional)"}
            <Textarea disabled={busy} maxLength={1000} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </label>
          {error && <p role="alert" className="text-sm text-coral">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => setSnapshot(undefined)}>Cancel</Button>
            <Button type="submit" size="sm" disabled={busy || status === snapshot.status || (correction && !notes.trim())}>
              {busy ? "Saving…" : correction ? "Record correction" : "Record move"}
            </Button>
          </div>
        </form>
      ) : <Button size="sm" variant="outline" onClick={open}>Move</Button>}
      <details className="border-t border-border pt-2 text-sm">
        <summary className="cursor-pointer">Recent history</summary>
        <ol className="mt-2 space-y-2">
          {item.application.events.slice(-10).reverse().map((event) => (
            <li key={event.requestId} className="break-words">
              {label(event.fromStatus)} → {label(event.toStatus)}
              {event.correction && " (correction)"}
              <time className="ml-2 text-muted-foreground" dateTime={event.createdAt}>{new Date(event.createdAt).toLocaleDateString()}</time>
              {event.notes && <p className="text-muted-foreground">{event.notes}</p>}
            </li>
          ))}
        </ol>
      </details>
    </article>
  );
}

export function PrivateDraftApplications() {
  const { data, error, mutate } = useSWR<DraftApplicationItem[]>("/api/job-drafts/applications");
  return (
    <BrutalCard id="private-drafts" className="scroll-mt-16 space-y-3">
      <h2 className="text-lg font-bold">Private draft applications</h2>
      <p className="text-sm text-muted-foreground">Track jobs you brought in from a link or pasted description.</p>
      {error && <div className="space-y-2"><p role="alert" className="text-sm text-coral">{errorSummary(error)}</p><Button size="sm" variant="outline" onClick={() => void mutate()}>Retry</Button></div>}
      {!data && !error && <p role="status" className="text-sm text-muted-foreground">Loading private applications…</p>}
      {data?.length === 0 && <Link href="/jobs/intake" className="text-sm text-purple underline">Bring a job to start tracking</Link>}
      {!!data?.length && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((item) => (
            <DraftCard key={item.draftId} item={item} refresh={() => { void mutate(); }} onSaved={(application) => {
              void mutate((current) => current?.map((entry) =>
                entry.draftId === item.draftId && entry.application.revision <= application.revision
                  ? { ...entry, application } : entry
              ));
            }} />
          ))}
        </div>
      )}
    </BrutalCard>
  );
}
