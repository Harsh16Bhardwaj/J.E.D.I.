"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Braces,
  Plus,
  RefreshCw,
  Upload,
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
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  apiRequest,
  errorSummary,
  isApiError,
  type BatchCreateResult,
  type BatchPage,
} from "@/lib/api";

const exampleTimestamp = new Date().toISOString();
const exampleDate = exampleTimestamp.slice(0, 10);
const exampleEnvelope = `{
  "externalBatchId": "daily-${exampleDate}-example",
  "schemaVersion": "1.0",
  "promptVersion": "jobs-v1",
  "generatedAt": "${exampleTimestamp}",
  "jobs": [
    {
      "companyName": "Example Labs",
      "roleTitle": "Backend Engineer",
      "description": "Build reliable Python services.",
      "applyUrl": "https://example.com/jobs/backend-engineer",
      "location": "Bengaluru",
      "workMode": "HYBRID",
      "postedAt": "${exampleTimestamp}",
      "skills": ["Python", "FastAPI", "PostgreSQL"]
    }
  ]
}`;

export default function BatchesPage() {
  const [all, setAll] = useState(false);
  const [page, setPage] = useState(1);
  const [importOpen, setImportOpen] = useState(false);
  const [source, setSource] = useState(exampleEnvelope);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<unknown>();
  const [result, setResult] = useState<BatchCreateResult>();
  const { mutate: mutateGlobal } = useSWRConfig();
  const endpoint = `/api/batches${all ? "/all" : ""}?page=${page}&pageSize=10`;
  const batches = useSWR<BatchPage>(endpoint);
  const pages = Math.max(1, Math.ceil((batches.data?.total ?? 0) / 10));

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setImportOpen(
        new URLSearchParams(window.location.search).get("import") === "1",
      );
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  function setView(showAll: boolean) {
    setAll(showAll);
    setPage(1);
  }

  async function loadJsonFile(file: File | undefined) {
    if (!file) return;
    setImportError(undefined);
    setResult(undefined);
    if (file.size > 5 * 1024 * 1024) {
      setImportError(new Error("The JSON file must be 5 MB or smaller."));
      return;
    }
    try {
      setSource(await file.text());
    } catch {
      setImportError(new Error("The selected file could not be read."));
    }
  }

  async function importBatch() {
    if (importing) return;
    setImportError(undefined);
    setResult(undefined);
    let body: unknown;
    try {
      body = JSON.parse(source);
    } catch {
      setImportError(new Error("The pasted content is not valid JSON."));
      return;
    }
    setImporting(true);
    try {
      const created = await apiRequest<BatchCreateResult>("/api/batches", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(created);
      setImportOpen(false);
      await mutateGlobal(
        (key) => typeof key === "string" && key.startsWith("/api/batches"),
        undefined,
        { revalidate: true },
      );
      toast.success(created.replayed ? "Existing batch restored." : "Batch imported.", {
        description: `${created.jobCount} unique jobs retained.`,
      });
    } catch (error) {
      setImportError(error);
      toast.error(errorSummary(error));
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="space-y-9">
      <RouteHeader
        eyebrow="Batch workspace"
        title="Control the daily intake."
        path="/batches"
        description="Imports are validated, limited to verified postings from the last 30 days, and deterministically deduplicated."
      />

      <div className="flex flex-wrap items-center justify-between gap-4 border-b-2 border-foreground pb-4">
        <div className="flex gap-2">
          <Button
            className={`min-h-11 cursor-pointer rounded-lg border ${!all ? "border-acid/30 bg-acid/10 text-acid" : "border-border bg-background text-foreground hover:border-acid/40 hover:bg-acid/10"}`}
            onClick={() => setView(false)}
          >
            Awaiting rank
          </Button>
          <Button
            className={`min-h-11 cursor-pointer rounded-lg border ${all ? "border-purple/30 bg-purple/10 text-purple" : "border-border bg-background text-foreground hover:border-purple/40 hover:bg-purple/10"}`}
            onClick={() => setView(true)}
          >
            All batches
          </Button>
        </div>
        <Button
          className="min-h-11 rounded-lg border border-border bg-foreground text-background hover:bg-acid"
          onClick={() => {
            setResult(undefined);
            setImportError(undefined);
            setImportOpen(true);
          }}
        >
          <Plus className="size-4" /> Import JSON
        </Button>
      </div>

      {batches.isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((item) => (
            <Skeleton key={item} className="h-28 border-2 border-foreground bg-raised" />
          ))}
        </div>
      ) : batches.error ? (
        <BrutalCard className="border-coral">
          <p className="ops-label text-coral">Could not load batches</p>
          <p className="mt-3 text-sm">{errorSummary(batches.error)}</p>
          <Button className="mt-5 min-h-11" onClick={() => void batches.mutate()}>
            <RefreshCw className="size-4" /> Retry
          </Button>
        </BrutalCard>
      ) : batches.data?.items.length ? (
        <div className="space-y-3" aria-busy={batches.isValidating}>
          {batches.isValidating && (
            <p className="ops-label text-purple">Refreshing cached results…</p>
          )}
          {batches.data.items.map((batch) => (
            <Link key={batch.id} href={`/batches/${batch.id}`} className="group block">
              <BrutalCard className="grid gap-5 bg-card transition-transform group-hover:-translate-y-1 group-hover:bg-raised md:grid-cols-[1.5fr_repeat(3,.55fr)_auto] md:items-center">
                <div>
                  <StatusBadge tone={batch.status === "FAILED" ? "warning" : "queued"}>
                    {batch.status}
                  </StatusBadge>
                  <h2 className="mt-3 text-xl font-black uppercase">
                    {batch.displayName ?? "Imported batch"}
                  </h2>
                  <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                    {batch.externalBatchId}
                  </p>
                  <p className="mt-1 font-mono text-xs text-muted-foreground">
                    {new Date(batch.createdAt).toLocaleString()}
                  </p>
                </div>
                {[
                  ["Retained", batch.jobCount],
                  ["Duplicates", batch.duplicateCount],
                  ["Received", batch.receivedCount],
                ].map(([label, value]) => (
                  <div key={label as string}>
                    <p className="text-2xl font-black">{value}</p>
                    <p className="ops-label mt-1 text-muted-foreground">{label}</p>
                  </div>
                ))}
                <ArrowUpRight className="size-6 text-acid transition-transform group-hover:translate-x-1 group-hover:-translate-y-1" />
              </BrutalCard>
            </Link>
          ))}
        </div>
      ) : (
        <BrutalCard className="bg-raised py-16 text-center">
          <Braces className="mx-auto size-9 text-acid" />
          <h2 className="mt-5 text-3xl font-black uppercase">Nothing here yet.</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Import one structured JSON envelope to begin.
          </p>
        </BrutalCard>
      )}

      <div className="flex items-center justify-between">
        <Button variant="outline" className="min-h-11 border-2" disabled={page === 1} onClick={() => setPage((value) => value - 1)}>
          <ArrowLeft className="size-4" /> Previous
        </Button>
        <span className="ops-label">Page {page} / {pages}</span>
        <Button variant="outline" className="min-h-11 border-2" disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>
          Next <ArrowRight className="size-4" />
        </Button>
      </div>

      <Dialog
        open={importOpen}
        onOpenChange={(open) => {
          if (!importing) setImportOpen(open);
        }}
      >
        <DialogContent
          showCloseButton={!importing}
          className="flex max-h-[90vh] flex-col overflow-hidden rounded-[4px] border-2 border-foreground sm:max-w-3xl"
        >
          <DialogHeader>
            <DialogTitle className="text-2xl font-black uppercase">
              Import a JSON batch
            </DialogTitle>
            <DialogDescription>
              One envelope enters validation, cleanup and deterministic dedupe.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap items-center gap-3 border border-border bg-raised/40 p-3">
            <label className="inline-flex min-h-10 cursor-pointer items-center gap-2 border border-border bg-background px-3 font-mono text-xs font-bold uppercase hover:border-acid hover:text-acid focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-acid">
              <Upload className="size-4" aria-hidden="true" /> Choose JSON file
              <input
                type="file"
                accept="application/json,.json"
                className="sr-only"
                disabled={importing}
                onChange={(event) => {
                  void loadJsonFile(event.target.files?.[0]);
                  event.target.value = "";
                }}
              />
            </label>
            <span className="text-xs text-muted-foreground">Maximum 5 MB, or paste the JSON below.</span>
          </div>
          <Textarea
            value={source}
            onChange={(event) => setSource(event.target.value)}
            disabled={importing}
            spellCheck={false}
            className="min-h-56 max-h-[48vh] flex-1 resize-y overflow-auto border-2 bg-background font-mono text-xs leading-5"
            aria-label="Batch JSON"
          />
          {Boolean(importError) && (
            <div role="alert" className="border-2 border-coral bg-coral/10 p-4">
              <p className="font-bold text-coral">{errorSummary(importError)}</p>
              {isApiError(importError) && importError.status === 409 && (
                <p className="mt-2 text-sm text-muted-foreground">
                  Choose a new externalBatchId, or paste the exact original
                  content to replay the existing batch.
                </p>
              )}
              {isApiError(importError) && importError.status === 422 && (
                <p className="mt-2 text-sm text-muted-foreground">
                  Review the validation details: no valid unique jobs remained
                  after validation and deduplication.
                </p>
              )}
              {isApiError(importError) && importError.requestId && (
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  Request ID: {importError.requestId}
                </p>
              )}
            </div>
          )}
          {result && (
            <div className="border-2 border-acid bg-acid/10 p-4">
              <p className="font-black uppercase text-acid">
                {result.replayed ? "Exact replay detected" : "Import complete"}
              </p>
              <p className="mt-2 text-sm">
                {result.jobCount} retained · {result.duplicateCount} duplicates ·{" "}
                {result.validationReport.length} invalid rows skipped
              </p>
              {result.validationReport.length > 0 && (
                <details className="mt-3">
                  <summary className="ops-label cursor-pointer text-muted-foreground">
                    Skipped source rows
                  </summary>
                  <p className="mt-2 font-mono text-xs">
                    {result.validationReport
                      .map((issue) => issue.sourceIndex + 1)
                      .join(", ")}
                  </p>
                </details>
              )}
              <Link href={`/batches/${result.batchId}`} className="ops-label mt-4 inline-flex min-h-11 items-center gap-2 text-acid">
                Open batch <ArrowUpRight className="size-4" />
              </Link>
            </div>
          )}
          <DialogFooter className="rounded-none">
            <Button
              className="min-h-11 rounded-lg border border-border bg-foreground text-background hover:bg-acid"
              disabled={importing}
              onClick={() => void importBatch()}
            >
              {importing ? "Validating and deduplicating…" : "Save batch"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
