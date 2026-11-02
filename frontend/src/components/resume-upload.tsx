"use client";

import { useState } from "react";
import { FileText, Upload, Check, LoaderCircle } from "lucide-react";
import useSWR from "swr";
import { toast } from "sonner";
import { apiRequest, errorSummary, isApiError } from "@/lib/api";
import type { ResumeEvidence } from "@/lib/learning";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { TagField } from "@/components/tag-field";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

export function ResumeUpload({
  onPendingChange,
}: {
  onPendingChange?: (pending: boolean) => void;
}) {
  const saved = useSWR<ResumeEvidence | null>("/api/resume");
  const [draft, setDraft] = useState<ResumeEvidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string>();
  const [invalid, setInvalid] = useState(false);
  const evidence = draft ?? saved.data;
  const [confirmed, setConfirmed] = useState(false);

  function edit<K extends keyof ResumeEvidence>(
    key: K,
    value: ResumeEvidence[K],
  ) {
    if (!evidence) return;
    setDraft({ ...evidence, [key]: value });
    setDirty(true);
    setConfirmed(false);
    onPendingChange?.(true);
  }

  async function upload(file?: File) {
    if (!file || busy) return;
    setError(undefined);
    if (
      !file.name.toLowerCase().endsWith(".pdf") ||
      file.size > 5 * 1024 * 1024
    ) {
      setError("Choose a PDF resume of 5 MB or less.");
      setInvalid(true);
      return;
    }
    setBusy(true);
    onPendingChange?.(true);
    const body = new FormData();
    body.append("file", file);
    try {
      const result = await apiRequest<ResumeEvidence>("/api/resume/extract", {
        method: "POST",
        body,
      });
      setDraft(result);
      setDirty(true);
      setConfirmed(false);
    } catch (cause) {
      setError(errorSummary(cause));
      setInvalid(isApiError(cause) && cause.status === 422);
      onPendingChange?.(dirty);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!evidence || busy) return;
    setBusy(true);
    setError(undefined);
    onPendingChange?.(true);
    try {
      const result = await apiRequest<ResumeEvidence>("/api/resume", {
        method: "PUT",
        body: JSON.stringify(evidence),
      });
      await saved.mutate(result, false);
      setDraft(null);
      setDirty(false);
      setConfirmed(true);
      onPendingChange?.(false);
      toast.success("Resume evidence saved privately.");
    } catch (cause) {
      setError(errorSummary(cause));
      onPendingChange?.(dirty);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="space-y-5 border-t border-border pt-6"
      aria-label="Resume upload"
    >
      <div className="flex items-center gap-3">
        <FileText className="size-5 text-purple" />
        <h2 className="text-xl font-semibold">Add your resume</h2>
        <span className="ops-label text-muted-foreground">Optional</span>
      </div>
      <p className="text-sm leading-6 text-muted-foreground">
        Extract your experience and skills for interview preparation. Your
        target titles, salary and location preferences stay under your control.
      </p>
      <label className="flex cursor-pointer items-center gap-4 rounded-xl border border-dashed border-purple/50 bg-purple/5 p-5 focus-within:ring-2 focus-within:ring-ring">
        {busy ? (
          <LoaderCircle className="size-6 animate-spin text-purple" />
        ) : (
          <Upload className="size-6 text-purple" />
        )}
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold">
            {busy ? "Processing resume…" : "Upload a PDF resume"}
          </span>
          <span className="mt-1 block text-xs text-muted-foreground">
            Text-based PDF · Up to 5 MB · 1–10 pages · No password
          </span>
          <input
            aria-label="Upload PDF resume"
            type="file"
            accept=".pdf,application/pdf"
            className="mt-3 block w-full text-xs file:mr-3 file:rounded file:border file:border-border file:bg-card file:px-3 file:py-2 file:text-foreground"
            disabled={busy || saved.isLoading}
            onChange={(event) => {
              void upload(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </span>
      </label>
      {saved.isLoading && (
        <p className="text-xs text-muted-foreground">Loading saved resume…</p>
      )}
      {saved.error && (
        <div role="alert" className="text-sm text-coral">
          {errorSummary(saved.error)}{" "}
          <Button
            type="button"
            variant="outline"
            onClick={() => void saved.mutate()}
          >
            Retry
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-coral">
          {error}
        </p>
      )}
      {evidence && (
        <fieldset disabled={busy} className="space-y-5">
          <legend className="mb-4 ops-label text-acid">
            Review extracted facts
          </legend>
          <p className="text-xs text-muted-foreground">
            These facts are private to you. Review and save before finishing
            onboarding. The original PDF is not stored.
          </p>
          <TagField
            id="resume-explicit"
            label="Explicitly mentioned skills"
            values={evidence.explicitSkills}
            suggestions={[]}
            placeholder="Add a skill and press Enter"
            onChange={(value) => edit("explicitSkills", value)}
          />
          <div>
            <p className="ops-label">Inferred skills · confirm proficiency</p>
            <div className="mt-2 space-y-2">
              {evidence.inferredSkills.length ? (
                evidence.inferredSkills.map((item, index) => (
                  <div
                    key={`${item.skill}-${index}`}
                    className="rounded-lg border border-purple/30 bg-purple/5 p-3"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <strong className="text-sm">{item.skill}</strong>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          edit(
                            "inferredSkills",
                            evidence.inferredSkills.filter(
                              (_, i) => i !== index,
                            ),
                          )
                        }
                      >
                        Remove
                      </Button>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {item.evidence}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  No inferred skills.
                </p>
              )}
            </div>
          </div>
          <label className="block space-y-2">
            <span className="ops-label">Summary</span>
            <Textarea
              value={evidence.summary}
              maxLength={5000}
              onChange={(e) => edit("summary", e.target.value)}
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block space-y-2">
              <span className="ops-label">Current location</span>
              <Input
                value={evidence.currentLocation ?? ""}
                maxLength={500}
                onChange={(e) =>
                  edit("currentLocation", e.target.value || null)
                }
                placeholder="Unknown"
              />
            </label>
            <label className="block space-y-2">
              <span className="ops-label">Work experience (years)</span>
              <Input
                type="number"
                min={0}
                max={80}
                step="0.01"
                value={evidence.experienceYears ?? ""}
                placeholder="Unknown"
                onChange={(e) =>
                  edit(
                    "experienceYears",
                    e.target.value === "" ? null : Number(e.target.value),
                  )
                }
              />
            </label>
          </div>
          {(
            [
              ["contact", "Contact details"],
              ["projects", "Projects"],
              ["workHistory", "Work history"],
              ["education", "Education"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="block space-y-2">
              <span className="ops-label">{label} · one entry per line</span>
              <Textarea
                value={evidence[key].join("\n")}
                onChange={(e) => edit(key, e.target.value.split("\n"))}
                onBlur={(e) =>
                  edit(
                    key,
                    e.target.value
                      .split("\n")
                      .map((x) => x.trim())
                      .filter(Boolean),
                  )
                }
              />
            </label>
          ))}
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">
              Extraction notes and source text
            </summary>
            <ul className="mt-3 list-disc space-y-2 pl-4">
              {evidence.limitations.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
            <pre className="mt-4 max-h-64 overflow-auto whitespace-pre-wrap font-sans leading-5">
              {evidence.text}
            </pre>
          </details>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              disabled={busy || (!dirty && !draft)}
              onClick={() => void save()}
            >
              <Check />
              {busy ? "Saving…" : "Save reviewed resume"}
            </Button>
            {dirty ? (
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  setDraft(null);
                  setDirty(false);
                  setError(undefined);
                  onPendingChange?.(false);
                }}
              >
                Discard changes
              </Button>
            ) : (
              <span className="text-xs text-acid">
                {confirmed ? "Resume saved" : "Saved resume"}
              </span>
            )}
          </div>
        </fieldset>
      )}
      <Dialog open={invalid} onOpenChange={setInvalid}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload a readable resume</DialogTitle>
            <DialogDescription>
              {error ?? "Please upload a valid PDF resume."}
            </DialogDescription>
          </DialogHeader>
          <Button type="button" onClick={() => setInvalid(false)}>
            Choose another file
          </Button>
        </DialogContent>
      </Dialog>
    </section>
  );
}
