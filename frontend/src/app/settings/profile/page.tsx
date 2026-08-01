"use client";

import { useState } from "react";
import { Check, FileText, Plus, UserRound } from "lucide-react";
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
  type ProfileDetail,
  type ProfileSummary,
  type ProfileWriteResult,
} from "@/lib/api";

type ProfileForm = {
  resumeText: string;
  titles: string;
  locations: string;
  skills: string;
  experienceMin: string;
  experienceMax: string;
  salaryMin: string;
  salaryMax: string;
  currency: string;
};

const emptyForm: ProfileForm = {
  resumeText: "",
  titles: "",
  locations: "",
  skills: "",
  experienceMin: "",
  experienceMax: "",
  salaryMin: "",
  salaryMax: "",
  currency: "INR",
};

const list = (value: string) =>
  value.split(",").map((item) => item.trim()).filter(Boolean);
const number = (value: string) => (value.trim() ? Number(value) : null);

function RequestError({ error }: { error: unknown }) {
  return (
    <div role="alert" className="rounded-lg border border-coral/35 bg-coral/5 p-3 text-sm text-coral">
      {errorSummary(error)}
      {isApiError(error) && error.requestId && (
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          Request {error.requestId}
        </p>
      )}
    </div>
  );
}

export default function ProfileSettingsPage() {
  const profiles = useSWR<ProfileSummary[]>("/api/profiles");
  const [selected, setSelected] = useState<string>();
  const selectedId =
    selected ??
    profiles.data?.find((profile) => profile.active)?.id ??
    profiles.data?.[0]?.id;
  const detail = useSWR<ProfileDetail>(
    selectedId ? `/api/profiles/${selectedId}` : null,
  );
  const [createOpen, setCreateOpen] = useState(false);
  const [activation, setActivation] = useState<ProfileSummary>();
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [requestError, setRequestError] = useState<unknown>();
  const { mutate } = useSWRConfig();

  function update<K extends keyof ProfileForm>(key: K, value: ProfileForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function refreshProfiles(id?: string) {
    await mutate(
      (key) => typeof key === "string" && key.startsWith("/api/profiles"),
      undefined,
      { revalidate: true },
    );
    if (id) setSelected(id);
  }

  async function createProfile() {
    if (busy) return;
    setRequestError(undefined);
    const expMin = number(form.experienceMin);
    const expMax = number(form.experienceMax);
    const salaryMin = number(form.salaryMin);
    const salaryMax = number(form.salaryMax);
    if (!form.resumeText.trim()) {
      setRequestError(new Error("Resume text is required."));
      return;
    }
    if (
      (expMin !== null && expMax !== null && expMin > expMax) ||
      (salaryMin !== null && salaryMax !== null && salaryMin > salaryMax)
    ) {
      setRequestError(new Error("Minimum values cannot exceed maximum values."));
      return;
    }
    setBusy(true);
    try {
      const result = await apiRequest<ProfileWriteResult>("/api/profiles", {
        method: "POST",
        body: JSON.stringify({
          resumeText: form.resumeText,
          preferredTitles: list(form.titles),
          preferredLocations: list(form.locations),
          preferredSkills: list(form.skills),
          experienceMinYears: expMin,
          experienceMaxYears: expMax,
          salaryMin,
          salaryMax,
          salaryCurrency: form.currency.trim() || null,
        }),
      });
      toast.success(result.replayed ? "Matching profile already exists." : "Profile version created.", {
        description: "New versions remain inactive until you activate one.",
      });
      await refreshProfiles(result.id);
      setCreateOpen(false);
      setForm(emptyForm);
    } catch (error) {
      setRequestError(error);
    } finally {
      setBusy(false);
    }
  }

  async function activateProfile() {
    if (!activation || busy) return;
    setBusy(true);
    setRequestError(undefined);
    try {
      const active = await apiRequest<ProfileDetail>(
        `/api/profiles/${activation.id}/activate`,
        { method: "POST" },
      );
      toast.success("Active profile changed.", {
        description: "Future normalization runs will pin this version.",
      });
      await refreshProfiles(active.id);
      setActivation(undefined);
    } catch (error) {
      setRequestError(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-9">
      <RouteHeader
        eyebrow="Candidate context"
        title="Profile versions"
        path="/settings/profile"
        description="Profiles are immutable snapshots. Activating one changes future preprocessing without rewriting past rankings."
      />

      <div className="flex justify-end">
        <Button className="min-h-11 rounded-lg bg-foreground px-4 text-background hover:bg-acid" onClick={() => {
          setRequestError(undefined);
          setCreateOpen(true);
        }}>
          <Plus className="size-4" /> New profile version
        </Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[.8fr_1.2fr]">
        <section className="space-y-3">
          <p className="ops-label text-muted-foreground">Version history</p>
          {profiles.isLoading ? (
            [0, 1, 2].map((item) => <Skeleton key={item} className="h-28 rounded-xl bg-raised" />)
          ) : profiles.error ? (
            <RequestError error={profiles.error} />
          ) : profiles.data?.length ? (
            profiles.data.map((profile) => (
              <button
                key={profile.id}
                type="button"
                onClick={() => setSelected(profile.id)}
                className={`w-full rounded-xl border p-4 text-left transition-colors ${selectedId === profile.id ? "border-acid/40 bg-acid/5" : "border-border bg-card hover:bg-raised"}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">
                    {new Date(profile.createdAt).toLocaleString()}
                  </span>
                  {profile.active && (
                    <span className="ops-label flex items-center gap-1 text-acid">
                      <Check className="size-3" /> Active
                    </span>
                  )}
                </div>
                <p className="mt-3 line-clamp-2 text-xs leading-5 text-muted-foreground">
                  {profile.resumePreview}
                </p>
              </button>
            ))
          ) : (
            <BrutalCard>
              <UserRound className="size-5 text-muted-foreground" />
              <p className="mt-5 text-sm text-muted-foreground">
                No profile exists. Create one before normalizing a batch.
              </p>
            </BrutalCard>
          )}
        </section>

        <section>
          <p className="ops-label mb-3 text-muted-foreground">Selected version</p>
          {detail.isLoading ? (
            <Skeleton className="h-[30rem] rounded-xl bg-raised" />
          ) : detail.data ? (
            <BrutalCard className="p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <FileText className="size-5 text-purple" />
                  <p className="mt-4 font-mono text-xs text-muted-foreground">
                    {detail.data.contentHash.slice(0, 16)}…
                  </p>
                </div>
                {!detail.data.active && (
                  <Button variant="outline" className="min-h-10 rounded-lg border-border" onClick={() => {
                    setRequestError(undefined);
                    setActivation(detail.data!);
                  }}>
                    Activate version
                  </Button>
                )}
              </div>
              <div className="mt-7 grid gap-5 sm:grid-cols-2">
                <div>
                  <p className="ops-label text-muted-foreground">Experience</p>
                  <p className="mt-2 text-sm">{detail.data.experienceMinYears ?? "Any"}–{detail.data.experienceMaxYears ?? "Any"} years</p>
                </div>
                <div>
                  <p className="ops-label text-muted-foreground">Salary</p>
                  <p className="mt-2 text-sm">{detail.data.salaryCurrency ?? ""} {detail.data.salaryMin?.toLocaleString() ?? "Any"}–{detail.data.salaryMax?.toLocaleString() ?? "Any"}</p>
                </div>
              </div>
              {[
                ["Titles", detail.data.preferredTitles],
                ["Locations", detail.data.preferredLocations],
                ["Skills", detail.data.preferredSkills],
              ].map(([label, values]) => (
                <div key={label as string} className="mt-6">
                  <p className="ops-label text-muted-foreground">{label as string}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(values as string[]).map((value) => (
                      <span key={value} className="rounded-full border border-border bg-raised px-3 py-1 text-xs">{value}</span>
                    ))}
                  </div>
                </div>
              ))}
              <div className="mt-7 border-t border-border pt-6">
                <p className="ops-label text-muted-foreground">Resume text</p>
                <p className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                  {detail.data.resumeText}
                </p>
              </div>
            </BrutalCard>
          ) : (
            <BrutalCard><p className="text-sm text-muted-foreground">Select or create a profile version.</p></BrutalCard>
          )}
        </section>
      </div>

      <Dialog open={createOpen} onOpenChange={(open) => !busy && setCreateOpen(open)}>
        <DialogContent showCloseButton={!busy} className="max-h-[92vh] overflow-y-auto rounded-xl border border-border sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-2xl font-semibold">Create profile version</DialogTitle>
            <DialogDescription>Comma-separate preference lists. The server normalizes whitespace and calculates provenance.</DialogDescription>
          </DialogHeader>
          <Textarea value={form.resumeText} onChange={(event) => update("resumeText", event.target.value)} placeholder="Paste resume text" className="min-h-44 border-border" />
          <Input value={form.titles} onChange={(event) => update("titles", event.target.value)} placeholder="Preferred titles: Backend Engineer, ML Engineer" />
          <Input value={form.locations} onChange={(event) => update("locations", event.target.value)} placeholder="Locations: Remote, Bengaluru" />
          <Input value={form.skills} onChange={(event) => update("skills", event.target.value)} placeholder="Skills: Python, FastAPI, PostgreSQL" />
          <div className="grid gap-3 sm:grid-cols-2">
            <Input type="number" min="0" value={form.experienceMin} onChange={(event) => update("experienceMin", event.target.value)} placeholder="Experience minimum" />
            <Input type="number" min="0" value={form.experienceMax} onChange={(event) => update("experienceMax", event.target.value)} placeholder="Experience maximum" />
            <Input type="number" min="0" value={form.salaryMin} onChange={(event) => update("salaryMin", event.target.value)} placeholder="Salary minimum" />
            <Input type="number" min="0" value={form.salaryMax} onChange={(event) => update("salaryMax", event.target.value)} placeholder="Salary maximum" />
          </div>
          <Input value={form.currency} maxLength={10} onChange={(event) => update("currency", event.target.value)} placeholder="Currency" />
          {Boolean(requestError) && <RequestError error={requestError} />}
          <DialogFooter className="rounded-none">
            <Button disabled={busy} className="min-h-11 bg-foreground text-background" onClick={() => void createProfile()}>
              {busy ? "Saving…" : "Create immutable version"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(activation)} onOpenChange={(open) => !open && !busy && setActivation(undefined)}>
        <DialogContent showCloseButton={!busy} className="rounded-xl border border-border sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold">Activate this profile?</DialogTitle>
            <DialogDescription>Only one version can be active. Existing prepared jobs and predictions remain pinned to their original profile.</DialogDescription>
          </DialogHeader>
          {Boolean(requestError) && <RequestError error={requestError} />}
          <DialogFooter className="rounded-none">
            <Button variant="outline" disabled={busy} onClick={() => setActivation(undefined)}>Cancel</Button>
            <Button disabled={busy} className="bg-foreground text-background" onClick={() => void activateProfile()}>
              {busy ? "Activating…" : "Activate profile"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
