"use client";

import { useState } from "react";
import {
  Activity,
  BrainCircuit,
  Check,
  ChevronRight,
  Flame,
  Plus,
} from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { RouteHeader } from "@/components/route-header";
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
  type ModelDetail,
  type ModelOperationResult,
  type ModelRuntimeHealth,
  type ModelRuntimeMetrics,
  type ModelSummary,
  type ModelWriteResult,
} from "@/lib/api";

const frontierManifest = JSON.stringify(
  {
    model: "xgb_conservative",
    variant: "stacked_drop5",
    trainingDataset: "ML/data/final/jedi_final_model_dataset.csv",
    artifactStatus: "not_exported",
  },
  null,
  2,
);

const frontierMetrics = JSON.stringify(
  {
    precisionAt25: 0.968,
    precisionAt25Std: 0.0438178,
    ndcgAt25: 0.9751577,
    ndcgAt25Std: 0.0340376,
    rocAuc: 0.9320887,
    averagePrecision: 0.9167378,
    evaluation: "StratifiedGroupKFold(5)",
    groupOverlap: 0,
  },
  null,
  2,
);

function ErrorBox({ error }: { error: unknown }) {
  return (
    <div role="alert" className="rounded-lg border border-coral/35 bg-coral/5 p-3 text-sm text-coral">
      {errorSummary(error)}
      {isApiError(error) && error.requestId && (
        <p className="mt-1 font-mono text-xs text-muted-foreground">Request {error.requestId}</p>
      )}
    </div>
  );
}

function JsonView({
  label,
  value,
}: {
  label: string;
  value: Record<string, unknown> | null;
}) {
  return (
    <div>
      <p className="ops-label text-muted-foreground">{label}</p>
      <pre className="mt-3 max-h-72 overflow-auto rounded-xl border border-border bg-[#0d0d0f] p-4 text-xs leading-6 text-muted-foreground">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </div>
  );
}

export default function ModelSettingsPage() {
  const models = useSWR<ModelSummary[]>("/api/models");
  const runtime = useSWR<ModelRuntimeHealth>("/health/model/live", {
    refreshInterval: 5000,
  });
  const runtimeMetrics = useSWR<ModelRuntimeMetrics>("/api/models/runtime/metrics");
  const [selected, setSelected] = useState<string>();
  const selectedId =
    selected ??
    models.data?.find((model) => model.active)?.id ??
    models.data?.[0]?.id;
  const detail = useSWR<ModelDetail>(
    selectedId ? `/api/models/${selectedId}` : null,
  );
  const deployment = useSWR<ModelOperationResult>(
    selectedId ? `/api/models/${selectedId}/deployment` : null,
  );
  const [createOpen, setCreateOpen] = useState(false);
  const [activation, setActivation] = useState<ModelSummary>();
  const [name, setName] = useState("jedi-frontier-xgb-stacked-drop5-v1");
  const [schemaVersion, setSchemaVersion] = useState("jedi-frontier-v1");
  const [manifest, setManifest] = useState(frontierManifest);
  const [metrics, setMetrics] = useState(frontierMetrics);
  const [busy, setBusy] = useState(false);
  const [requestError, setRequestError] = useState<unknown>();
  const { mutate } = useSWRConfig();

  async function refreshModels(id?: string) {
    await mutate(
      (key) => typeof key === "string" && key.startsWith("/api/models"),
      undefined,
      { revalidate: true },
    );
    if (id) setSelected(id);
  }

  async function createModel() {
    if (busy) return;
    setRequestError(undefined);
    let artifactManifest: Record<string, unknown>;
    let offlineMetrics: Record<string, unknown> | null;
    try {
      artifactManifest = JSON.parse(manifest) as Record<string, unknown>;
      offlineMetrics = metrics.trim()
        ? (JSON.parse(metrics) as Record<string, unknown>)
        : null;
    } catch {
      setRequestError(new Error("Manifest and metrics must contain valid JSON."));
      return;
    }
    if (!name.trim() || !schemaVersion.trim()) {
      setRequestError(new Error("Model name and feature schema version are required."));
      return;
    }
    setBusy(true);
    try {
      const result = await apiRequest<ModelWriteResult>("/api/models", {
        method: "POST",
        body: JSON.stringify({
          name,
          featureSchemaVersion: schemaVersion,
          artifactManifest,
          metrics: offlineMetrics,
        }),
      });
      toast.success(result.replayed ? "Matching model metadata already exists." : "Model metadata registered.", {
        description: "Registration does not load or execute an artifact.",
      });
      await refreshModels(result.id);
      setCreateOpen(false);
    } catch (error) {
      setRequestError(error);
    } finally {
      setBusy(false);
    }
  }

  async function activateModel() {
    if (!activation || busy) return;
    setBusy(true);
    setRequestError(undefined);
    try {
      const active = await apiRequest<ModelDetail>(
        `/api/models/${activation.id}/activate`,
        { method: "POST" },
      );
      toast.success("Active model changed.", {
        description: "Future ranking runs will pin this metadata version.",
      });
      await refreshModels(active.id);
      setActivation(undefined);
    } catch (error) {
      setRequestError(error);
    } finally {
      setBusy(false);
    }
  }

  async function registerEmbedded() {
    if (busy) return;
    setBusy(true);
    setRequestError(undefined);
    try {
      const result = await apiRequest<ModelWriteResult>(
        "/api/models/runtime/register",
        { method: "POST" },
      );
      toast.success(result.replayed ? "Embedded bundle already registered." : "Embedded bundle registered.");
      await refreshModels(result.id);
      await runtime.mutate();
      await deployment.mutate();
    } catch (error) {
      setRequestError(error);
    } finally {
      setBusy(false);
    }
  }

  async function warmupRuntime() {
    if (busy) return;
    setBusy(true);
    setRequestError(undefined);
    try {
      const result = await apiRequest<ModelOperationResult>(
        "/api/models/runtime/warmup",
        { method: "POST" },
      );
      toast.success("Embedded model is ready.", {
        description: `Load ${Math.round(result.runtime.modelLoadMs ?? 0)} ms · smoke ${Math.round(result.runtime.smokeTestMs ?? 0)} ms`,
      });
      await runtime.mutate();
      await deployment.mutate();
    } catch (error) {
      setRequestError(error);
    } finally {
      setBusy(false);
    }
  }

  async function deploymentCheck(modelId: string) {
    if (busy) return;
    setBusy(true);
    setRequestError(undefined);
    try {
      const result = await apiRequest<ModelOperationResult>(
        `/api/models/${modelId}/deployment-check`,
        { method: "POST" },
      );
      toast.success("Artifact and contracts are compatible.", {
        description: `Check ${result.checkId}`,
      });
      await runtime.mutate();
      await deployment.mutate();
    } catch (error) {
      setRequestError(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-9">
      <RouteHeader
        eyebrow="Model registry"
        title="Model versions"
        path="/settings/models"
        description="Register immutable manifests and evaluation evidence, inspect provenance, and explicitly choose the version future ranking runs will pin."
      />

      <BrutalCard className="flex flex-wrap items-center justify-between gap-4 bg-raised">
        <div>
          <p className="ops-label text-purple">Embedded runtime</p>
          <p className="mt-2 flex items-center gap-2 text-sm font-bold">
            <Activity className="size-4" /> {runtime.data?.state ?? "CHECKING"}
          </p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            {runtime.data?.artifactHash?.slice(0, 18) ?? "No artifact loaded"}
            {runtime.data?.modelLoadMs != null ? ` · ${Math.round(runtime.data.modelLoadMs)} ms load` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="min-h-11 border-2" disabled={busy} onClick={() => void warmupRuntime()}>
            <Flame className="size-4" /> Warm up
          </Button>
          <Button variant="outline" className="min-h-11 border-2" disabled={busy} onClick={() => void registerEmbedded()}>
            <BrainCircuit className="size-4" /> Register embedded bundle
          </Button>
        </div>
      </BrutalCard>

      {runtimeMetrics.data && (
        <div className="grid gap-3 sm:grid-cols-4">
          {[
            ["Latest 20 runs", runtimeMetrics.data.sampleSize],
            ["Failure rate", `${(runtimeMetrics.data.failureRate * 100).toFixed(1)}%`],
            ["Cold-start rate", `${(runtimeMetrics.data.coldStartRate * 100).toFixed(1)}%`],
            ["Warm p95", runtimeMetrics.data.p95ExecutionMs == null ? "No data" : `${Math.round(runtimeMetrics.data.p95ExecutionMs)} ms`],
          ].map(([label, value]) => (
            <BrutalCard key={label} className="bg-card">
              <p className="ops-label text-muted-foreground">{label}</p>
              <p className="mt-3 text-2xl font-black">{value}</p>
            </BrutalCard>
          ))}
          {runtimeMetrics.data.warnings.length > 0 && (
            <div className="border-2 border-coral bg-coral/10 p-3 text-sm text-coral sm:col-span-4">
              {runtimeMetrics.data.warnings.join(" · ")}
            </div>
          )}
        </div>
      )}

      {Boolean(requestError) && <ErrorBox error={requestError} />}

      <div className="flex justify-end">
        <Button
          className="min-h-11 rounded-lg bg-foreground px-4 text-background hover:bg-acid"
          onClick={() => {
            setRequestError(undefined);
            setCreateOpen(true);
          }}
        >
          <Plus className="size-4" /> Register metadata
        </Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
        <section className="space-y-3">
          <p className="ops-label text-muted-foreground">Registry</p>
          {models.isLoading ? (
            [0, 1, 2].map((item) => <Skeleton key={item} className="h-24 rounded-xl bg-raised" />)
          ) : models.error ? (
            <ErrorBox error={models.error} />
          ) : models.data?.length ? (
            models.data.map((model) => (
              <button
                key={model.id}
                type="button"
                onClick={() => setSelected(model.id)}
                className={`flex w-full items-center justify-between gap-4 rounded-xl border p-4 text-left transition-colors ${selectedId === model.id ? "border-purple/45 bg-purple/5" : "border-border bg-card hover:bg-raised"}`}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">{model.name}</p>
                    {model.active && (
                      <span className="ops-label flex items-center gap-1 text-acid">
                        <Check className="size-3" /> Active
                      </span>
                    )}
                  </div>
                  <p className="mt-2 font-mono text-xs text-muted-foreground">
                    schema / {model.featureSchemaVersion}
                  </p>
                </div>
                <ChevronRight className="size-4 text-muted-foreground" />
              </button>
            ))
          ) : (
            <BrutalCard>
              <BrainCircuit className="size-5 text-muted-foreground" />
              <p className="mt-5 text-sm text-muted-foreground">
                No model metadata is registered. The form is prefilled with the
                verified frontier experiment.
              </p>
            </BrutalCard>
          )}
        </section>

        <section>
          <p className="ops-label mb-3 text-muted-foreground">Model card</p>
          {detail.isLoading ? (
            <Skeleton className="h-[32rem] rounded-xl bg-raised" />
          ) : detail.data ? (
            <BrutalCard className="p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <BrainCircuit className="size-5 text-purple" />
                  <h2 className="mt-4 text-2xl font-semibold">{detail.data.name}</h2>
                  <p className="mt-2 font-mono text-xs text-muted-foreground">
                    {detail.data.contentHash.slice(0, 18)}… · {new Date(detail.data.createdAt).toLocaleString()}
                  </p>
                </div>
                {!detail.data.active && (
                  <div className="flex flex-wrap gap-2">
                    {detail.data.featureSchemaVersion === "prepared-job-v2" && (
                      <Button
                        variant="outline"
                        className="min-h-10 rounded-lg border-border"
                        disabled={busy}
                        onClick={() => void deploymentCheck(detail.data!.id)}
                      >
                        Check deployment
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      className="min-h-10 rounded-lg border-border"
                      onClick={() => {
                        setRequestError(undefined);
                        setActivation(detail.data!);
                      }}
                    >
                      Activate version
                    </Button>
                  </div>
                )}
              </div>
              <div className="my-7 rounded-xl border border-border bg-raised/50 p-4">
                <p className="ops-label text-muted-foreground">Feature contract</p>
                <p className="mt-2 text-sm">{detail.data.featureSchemaVersion}</p>
              </div>
              <div className="space-y-6">
                <JsonView
                  label={`Deployment / ${deployment.data?.status ?? "unchecked"}`}
                  value={deployment.data?.details ?? null}
                />
                <JsonView label="Offline metrics" value={detail.data.metrics} />
                <JsonView label="Artifact manifest" value={detail.data.artifactManifest} />
              </div>
            </BrutalCard>
          ) : (
            <BrutalCard><p className="text-sm text-muted-foreground">Select or register a model version.</p></BrutalCard>
          )}
        </section>
      </div>

      <Dialog open={createOpen} onOpenChange={(open) => !busy && setCreateOpen(open)}>
        <DialogContent showCloseButton={!busy} className="max-h-[92vh] overflow-y-auto rounded-xl border border-border sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-2xl font-semibold">Register model metadata</DialogTitle>
            <DialogDescription>This records provenance only. It does not upload, load or execute a model artifact.</DialogDescription>
          </DialogHeader>
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Unique model name" />
          <Input value={schemaVersion} onChange={(event) => setSchemaVersion(event.target.value)} placeholder="Feature schema version" />
          <div>
            <label className="ops-label text-muted-foreground">Artifact manifest JSON</label>
            <Textarea value={manifest} onChange={(event) => setManifest(event.target.value)} className="mt-2 min-h-40 border-border font-mono text-xs" />
          </div>
          <div>
            <label className="ops-label text-muted-foreground">Offline metrics JSON</label>
            <Textarea value={metrics} onChange={(event) => setMetrics(event.target.value)} className="mt-2 min-h-48 border-border font-mono text-xs" />
          </div>
          {Boolean(requestError) && <ErrorBox error={requestError} />}
          <DialogFooter className="rounded-none">
            <Button disabled={busy} className="min-h-11 bg-foreground text-background" onClick={() => void createModel()}>
              {busy ? "Registering…" : "Register immutable metadata"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(activation)} onOpenChange={(open) => !open && !busy && setActivation(undefined)}>
        <DialogContent showCloseButton={!busy} className="rounded-xl border border-border sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold">Activate this model?</DialogTitle>
            <DialogDescription>Only one model can be active. Completed and queued runs keep their pinned version history.</DialogDescription>
          </DialogHeader>
          {Boolean(requestError) && <ErrorBox error={requestError} />}
          <DialogFooter className="rounded-none">
            <Button variant="outline" disabled={busy} onClick={() => setActivation(undefined)}>Cancel</Button>
            <Button disabled={busy} className="bg-foreground text-background" onClick={() => void activateModel()}>
              {busy ? "Activating…" : "Activate model"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
