"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, DatabaseZap, FileUp } from "lucide-react";
import { toast } from "sonner";
import useSWR from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { RouteHeader } from "@/components/route-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { apiRequest, errorSummary, isApiError, type User } from "@/lib/api";

type ImportResult = {
  batchId: string; receivedCount: number; importedCount: number;
  duplicateCount: number; invalidCount: number; trainingExampleCount: number;
  featureSchemaVersion: string; replayed: boolean;
  validationReport: Array<{ row: number; message: string }>;
};

export default function TrainingDataPage() {
  const session = useSWR<User>("/api/auth/session");
  const [file, setFile] = useState<File>();
  const [result, setResult] = useState<ImportResult>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);

  async function upload() {
    if (!file || busy) return;
    setBusy(true); setError(undefined);
    try {
      const body = new FormData(); body.append("file", file);
      const imported = await apiRequest<ImportResult>(
        "/api/misc/training-data/import-csv", { method: "POST", body },
      );
      setResult(imported);
      toast.success(imported.replayed ? "CSV was already imported." : "Training CSV imported.");
    } catch (caught) {
      setError(caught); toast.error(errorSummary(caught));
    } finally { setBusy(false); }
  }

  if (session.data && !session.data.isGroupOwner) {
    return <BrutalCard className="border-purple/30"><p className="ops-label text-purple">Shared model governance</p><h1 className="mt-3 text-3xl font-semibold">Owner access required</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">Your reviews and application activity remain private. Only the group owner can promote labels or import rows into the shared model training dataset.</p><Link className={buttonVariants({ variant: "outline", className: "mt-6" })} href="/jobs">Return to your jobs</Link></BrutalCard>;
  }

  return (
    <div className="space-y-8">
      <RouteHeader eyebrow="Misc functionality" path="/misc/training-data" title="Training data intake" description="Bootstrap the private training database or append a labeled CSV without bypassing job, profile, annotation or feature provenance." />
      <div className="grid gap-5 lg:grid-cols-[1.15fr_.85fr]">
        <BrutalCard className="bg-card">
          <div className="flex items-center gap-3"><FileUp className="size-5 text-acid" /><h2 className="text-xl font-semibold">Upload CSV</h2></div>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">Activate a profile first. JEDI accepts the canonical frontier dataset columns or job CSV columns such as company_name, role_title, description and apply_url. Complete label columns are written directly to TrainingExample.</p>
          <label className="mt-6 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-border bg-raised/40 p-6 text-center hover:border-acid/40">
            <DatabaseZap className="size-7 text-purple" />
            <span className="mt-3 text-sm font-medium">{file?.name ?? "Choose a UTF-8 CSV"}</span>
            <span className="mt-1 text-xs text-muted-foreground">No application-level file-size cap</span>
            <input className="sr-only" type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0]); setResult(undefined); setError(undefined); }} />
          </label>
          {Boolean(error) && <div role="alert" className="mt-4 rounded-lg border border-coral/30 bg-coral/10 p-4 text-sm text-coral"><p>{errorSummary(error)}</p>{isApiError(error) && error.requestId && <p className="mt-2 font-mono text-xs">Request {error.requestId}</p>}</div>}
          <Button className="mt-5 min-h-11" disabled={!file || busy} onClick={() => void upload()}>{busy ? "Importing..." : "Parse and import"}</Button>
        </BrutalCard>
        <BrutalCard className="bg-raised">
          <p className="ops-label text-purple">Import contract</p>
          <ol className="mt-5 space-y-4 text-sm text-muted-foreground">
            <li><b className="text-foreground">01 / Parse</b><br />CSV becomes a stored JSON provenance envelope.</li>
            <li><b className="text-foreground">02 / Protect</b><br />Appended job CSVs are deduplicated. The canonical frontier bootstrap preserves all labeled rows and their evaluation groups.</li>
            <li><b className="text-foreground">03 / Preserve</b><br />Jobs, prepared features and labels retain their active-profile version.</li>
            <li><b className="text-foreground">04 / Train</b><br />Only rows with all ten required labels enter TrainingExample.</li>
          </ol>
          <a className="mt-7 inline-flex text-xs font-semibold text-acid" href="http://localhost:8000/api/training-examples/export.csv">Download current training CSV</a>
        </BrutalCard>
      </div>
      {result && <BrutalCard className="bg-card"><div className="flex flex-wrap items-center justify-between gap-5"><div><p className="ops-label text-acid">{result.replayed ? "Idempotent replay" : "Import complete"}</p><h2 className="mt-2 text-2xl font-semibold">{result.importedCount} jobs retained / {result.trainingExampleCount} training rows</h2><p className="mt-2 text-sm text-muted-foreground">{result.duplicateCount} duplicates / {result.invalidCount} invalid / schema {result.featureSchemaVersion}</p></div><Link className={buttonVariants()} href={`/misc/annotation/${result.batchId}`}>Review annotations <ArrowRight className="size-4" /></Link></div>{result.validationReport.length > 0 && <details className="mt-5 border-t border-border pt-4"><summary className="cursor-pointer text-sm text-coral">Inspect skipped rows</summary><ul className="mt-3 space-y-2 text-xs text-muted-foreground">{result.validationReport.map((issue) => <li key={`${issue.row}-${issue.message}`}>Row {issue.row}: {issue.message}</li>)}</ul></details>}</BrutalCard>}
    </div>
  );
}
