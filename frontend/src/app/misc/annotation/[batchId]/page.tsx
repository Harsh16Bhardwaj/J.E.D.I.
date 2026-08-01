"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Check, ChevronDown, DatabaseZap, Save } from "lucide-react";
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
import { apiRequest, errorSummary, type BatchSummary, type User } from "@/lib/api";

const scores = [
  { label: "Title fit", key: "roleTitleFit", max: 5, help: "How closely the title matches roles you want." },
  { label: "Role-family fit", key: "roleFamilyFit", max: 5, help: "Whether the broader career family is right." },
  { label: "Seniority fit", key: "seniorityFit", max: 5, help: "Whether the expected level suits your experience." },
  { label: "Location fit", key: "locationFit", max: 5, help: "How well the location matches your preferences." },
  { label: "Work-mode fit", key: "workModeFit", max: 5, help: "Remote, hybrid or onsite preference match." },
  { label: "Experience fit", key: "experienceFit", max: 5, help: "How realistically your experience matches." },
  { label: "Skills fit", key: "skillsFit", max: 5, help: "How strongly your current skills overlap." },
  { label: "Salary fit", key: "salaryFit", max: 8, help: "Salary attractiveness on the historical 0-8 scale." },
  { label: "Overall fit", key: "overallPreference", max: 5, help: "Your final holistic preference for this job." },
] as const;

type ScoreKey = (typeof scores)[number]["key"];
type Annotation = {
  relevanceLabel: string | null;
  applyLabel: boolean | null;
} & Record<ScoreKey, number | null>;
type Row = Annotation & {
  jobId: string;
  code: string;
  companyName: string;
  roleTitle: string;
  roleFamily: string | null;
  seniority: string | null;
  location: string | null;
  workMode: string | null;
  employmentType: string | null;
  applyUrl: string;
  complete: boolean;
  prepared: boolean;
  inTraining: boolean;
};
type Editor = {
  batch: BatchSummary;
  rows: Row[];
  completeCount: number;
  preparedCount: number;
  trainingCount: number;
};

function scoreOptions(max: number) {
  return [
    <option key="blank" value="">Not set</option>,
    ...Array.from({ length: max + 1 }, (_, value) => (
      <option key={value} value={value}>{value}</option>
    )),
  ];
}

function annotationOf(row: Row): Annotation {
  return {
    relevanceLabel: row.relevanceLabel,
    applyLabel: row.applyLabel,
    ...Object.fromEntries(scores.map(({ key }) => [key, row[key]])),
  } as Annotation;
}

function missingLabels(annotation: Annotation) {
  const missing: string[] = [];
  if (annotation.applyLabel === null) missing.push("Apply decision");
  for (const score of scores) {
    if (annotation[score.key] === null) missing.push(score.label);
  }
  return missing;
}

export default function AnnotationEditorPage() {
  const { batchId } = useParams<{ batchId: string }>();
  const { mutate: mutateGlobal } = useSWRConfig();
  const session = useSWR<User>("/api/auth/session");
  const editor = useSWR<Editor>(`/api/misc/batches/${batchId}/annotation-editor`);
  const [drafts, setDrafts] = useState<Record<string, Annotation>>({});
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("company");
  const [selection, setSelection] = useState("ALL_ANNOTATED");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const rows = useMemo(() => {
    const source = editor.data?.rows ?? [];
    return source
      .filter((row) => {
        const current = drafts[row.jobId] ?? annotationOf(row);
        const complete = missingLabels(current).length === 0;
        const matches = `${row.companyName} ${row.roleTitle} ${row.code}`
          .toLowerCase()
          .includes(search.toLowerCase());
        return matches && (
          filter === "all" ||
          (filter === "complete" && complete) ||
          (filter === "missing" && !complete) ||
          (filter === "training" && row.inTraining)
        );
      })
      .sort((left, right) => {
        if (sort === "role") return left.roleTitle.localeCompare(right.roleTitle);
        if (sort === "status") {
          const leftMissing = missingLabels(drafts[left.jobId] ?? annotationOf(left)).length;
          const rightMissing = missingLabels(drafts[right.jobId] ?? annotationOf(right)).length;
          return leftMissing - rightMissing;
        }
        return left.companyName.localeCompare(right.companyName);
      });
  }, [drafts, editor.data, filter, search, sort]);

  function edit(row: Row, key: keyof Annotation, value: string) {
    const current = drafts[row.jobId] ?? annotationOf(row);
    let parsed: string | number | boolean | null = value || null;
    if (key === "applyLabel") parsed = value === "" ? null : value === "true";
    if (scores.some((score) => score.key === key)) {
      parsed = value === "" ? null : Number(value);
    }
    setDrafts((all) => ({
      ...all,
      [row.jobId]: { ...current, [key]: parsed },
    }));
  }

  async function save() {
    const changedCount = Object.keys(drafts).length;
    if (!changedCount || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      await apiRequest(`/api/batches/${batchId}/annotations`, {
        method: "PATCH",
        body: JSON.stringify({
          annotations: Object.entries(drafts).map(([jobId, values]) => ({ jobId, ...values })),
        }),
      });
      setDrafts({});
      await editor.mutate();
      toast.success(`${changedCount} job annotation${changedCount === 1 ? "" : "s"} saved.`);
    } catch (caught) {
      setError(errorSummary(caught));
      toast.error(errorSummary(caught));
    } finally {
      setBusy(false);
    }
  }

  async function addToTraining() {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const result = await apiRequest<{ addedOrUpdatedCount: number }>(
        `/api/batches/${batchId}/training-examples`,
        { method: "POST", body: JSON.stringify({ selection }) },
      );
      toast.success(`${result.addedOrUpdatedCount} training rows added or refreshed.`);
      setConfirm(false);
      await editor.mutate();
      await mutateGlobal((key) => typeof key === "string" && key.includes("training"));
    } catch (caught) {
      setError(errorSummary(caught));
      toast.error(errorSummary(caught));
    } finally {
      setBusy(false);
    }
  }

  if (editor.isLoading) {
    return <div className="space-y-4"><Skeleton className="h-28 bg-raised" /><Skeleton className="h-96 bg-raised" /></div>;
  }
  if (!editor.data) {
    return <div role="alert" className="rounded-xl border border-coral/40 bg-card p-6"><h1 className="text-2xl font-semibold">Editor unavailable</h1><p className="mt-2 text-sm text-coral">{errorSummary(editor.error)}</p></div>;
  }

  const data = editor.data;
  const dirty = Object.keys(drafts).length;
  const detailedScores = scores.filter(({ key }) => key !== "overallPreference");

  return (
    <div className="space-y-6">
      <div>
        <Link href={`/batches/${batchId}`} className="inline-flex min-h-11 items-center gap-2 text-xs text-muted-foreground hover:text-acid">
          <ArrowLeft className="size-4" /> Back to batch
        </Link>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-5">
          <div>
            <p className="ops-label text-purple">Training feedback</p>
            <h1 className="mt-2 text-3xl font-semibold sm:text-5xl">Teach the next model</h1>
            <p className="mt-2 text-sm text-muted-foreground">{data.batch.externalBatchId} / {data.rows.length} jobs</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={!dirty || busy} onClick={() => void save()}>
              <Save className="size-4" /> Save {dirty || ""} changed
            </Button>
            {session.data?.isGroupOwner && (
              <Button disabled={Boolean(dirty) || !data.completeCount || !data.preparedCount} onClick={() => setConfirm(true)}>
                <DatabaseZap className="size-4" /> Add saved labels to training
              </Button>
            )}
          </div>
        </div>
      </div>

      <BrutalCard className="border-purple/40 bg-purple/10">
        <p className="ops-label text-purple">What is important here?</p>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div><p className="font-bold">Apply decision</p><p className="mt-1 text-sm text-muted-foreground">The yes/no target used to retrain the XGBoost apply classifier.</p></div>
          <div><p className="font-bold">Nine fit scores</p><p className="mt-1 text-sm text-muted-foreground">Human targets used to retrain the Ridge preference predictors.</p></div>
          <div><p className="font-bold">Relevance</p><p className="mt-1 text-sm text-muted-foreground">An optional personal workflow label. It is not a model target.</p></div>
        </div>
        <p className="mt-4 border-t border-purple/20 pt-4 text-sm text-muted-foreground">
          Saving annotations does not change today&apos;s ranking. Only complete labels that an owner promotes to training data can be included in a later offline retraining and model activation.
        </p>
      </BrutalCard>

      <div className="grid gap-3 sm:grid-cols-4">
        {[
          [data.completeCount, "saved complete"],
          [data.rows.length - data.completeCount, "still incomplete"],
          [data.preparedCount, "prepared jobs"],
          [data.trainingCount, "already in training"],
        ].map(([value, label]) => (
          <div key={label} className="rounded-xl border border-border bg-card p-4">
            <p className="text-2xl font-semibold">{value}</p>
            <p className="mt-1 text-xs text-muted-foreground">{label}</p>
          </div>
        ))}
      </div>

      {error && <div role="alert" className="rounded-lg border border-coral/30 bg-coral/10 p-3 text-sm text-coral">{error}</div>}

      <div className="grid gap-3 rounded-xl border border-border bg-card p-3 md:grid-cols-[1fr_11rem_11rem]">
        <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter company, role or code" />
        <select className="rounded-lg border border-input bg-background px-3 text-sm" value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">All jobs</option>
          <option value="missing">Needs labels</option>
          <option value="complete">Complete</option>
          <option value="training">In training</option>
        </select>
        <select className="rounded-lg border border-input bg-background px-3 text-sm" value={sort} onChange={(event) => setSort(event.target.value)}>
          <option value="company">Sort company</option>
          <option value="role">Sort role</option>
          <option value="status">Most complete first</option>
        </select>
      </div>

      <div className="space-y-3">
        {rows.map((row) => {
          const value = drafts[row.jobId] ?? annotationOf(row);
          const missing = missingLabels(value);
          const changed = Boolean(drafts[row.jobId]);
          const state = changed
            ? (missing.length ? `Unsaved / ${missing.length} required left` : "Ready to save")
            : (row.complete ? "Saved complete" : "Not complete");
          return (
            <BrutalCard key={row.jobId} className="bg-card">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <a href={row.applyUrl} target="_blank" rel="noreferrer" className="text-lg font-semibold hover:text-acid">{row.roleTitle}</a>
                  <p className="mt-1 text-sm text-muted-foreground">{row.companyName} / {row.location ?? "unknown location"}</p>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">{row.code}</p>
                </div>
                <div className="text-right text-xs">
                  <p className={missing.length ? (changed ? "text-purple" : "text-muted-foreground") : "text-acid"}>
                    {!missing.length && <Check className="mr-1 inline size-3" />}{state}
                  </p>
                  {row.inTraining && <p className="mt-1 text-purple">Already in training</p>}
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-3">
                <label className="space-y-2 text-sm"><span className="font-bold">Personal relevance <span className="font-normal text-muted-foreground">optional</span></span><select className="min-h-11 w-full rounded-md border border-input bg-background p-2" value={value.relevanceLabel ?? ""} onChange={(event) => edit(row, "relevanceLabel", event.target.value)}><option value="">Not set</option><option>DREAM</option><option>STRONG_APPLY</option><option>CONSIDER</option><option>REJECT</option></select></label>
                <label className="space-y-2 text-sm"><span className="font-bold">Would you apply? <span className="text-coral">required</span></span><select className="min-h-11 w-full rounded-md border border-input bg-background p-2" value={value.applyLabel === null ? "" : String(value.applyLabel)} onChange={(event) => edit(row, "applyLabel", event.target.value)}><option value="">Not set</option><option value="true">Yes</option><option value="false">No</option></select></label>
                <label className="space-y-2 text-sm"><span className="font-bold">Overall fit / 5 <span className="text-coral">required</span></span><select className="min-h-11 w-full rounded-md border border-input bg-background p-2" value={value.overallPreference ?? ""} onChange={(event) => edit(row, "overallPreference", event.target.value)}>{scoreOptions(5)}</select></label>
              </div>

              <details className="group mt-4 rounded-lg border border-border bg-raised/40 p-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-bold">
                  Detailed fit labels <span className="text-xs font-normal text-muted-foreground">8 required</span>
                  <ChevronDown className="size-4 transition-transform group-open:rotate-180" />
                </summary>
                <p className="mt-2 text-xs text-muted-foreground">Use 0 for a poor match, 3 for acceptable, and 5 for excellent. Salary retains the model&apos;s historical 0-8 scale.</p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {detailedScores.map((score) => (
                    <label key={score.key} className="space-y-2 text-sm">
                      <span className="font-bold">{score.label} / {score.max}</span>
                      <span className="block min-h-8 text-xs text-muted-foreground">{score.help}</span>
                      <select aria-label={`${score.label} for ${row.roleTitle}`} className="min-h-11 w-full rounded-md border border-input bg-background p-2" value={value[score.key] ?? ""} onChange={(event) => edit(row, score.key, event.target.value)}>{scoreOptions(score.max)}</select>
                    </label>
                  ))}
                </div>
              </details>
            </BrutalCard>
          );
        })}
        {!rows.length && <p className="rounded-xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">No jobs match these filters.</p>}
      </div>

      <Dialog open={confirm} onOpenChange={(open) => { if (!busy) setConfirm(open); }}>
        <DialogContent showCloseButton={!busy}>
          <DialogHeader>
            <DialogTitle>Add saved annotations to future training?</DialogTitle>
            <DialogDescription>This freezes prepared features and complete labels into versioned training examples. It does not retrain or change the active model immediately.</DialogDescription>
          </DialogHeader>
          <select className="min-h-11 rounded-lg border border-input bg-background px-3 text-sm" value={selection} onChange={(event) => setSelection(event.target.value)}>
            <option value="ALL_ANNOTATED">All complete annotations</option>
            <option value="YES_ONLY">Apply yes only</option>
            <option value="NO_ONLY">Apply no only</option>
          </select>
          {error && <p className="text-sm text-coral">{error}</p>}
          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setConfirm(false)}>Cancel</Button>
            <Button disabled={busy} onClick={() => void addToTraining()}>{busy ? "Adding..." : "Confirm and add"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
