"use client";

import { useState } from "react";
import { ArrowRight, BrainCircuit, Check, Database, UserRound } from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { TagField } from "@/components/tag-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  apiRequest,
  errorSummary,
  isApiError,
  type OnboardingResult,
  type OnboardingState,
} from "@/lib/api";

type FormState = {
  resumeText: string;
  preferredTitles: string[];
  preferredLocations: string[];
  preferredSkills: string[];
  experienceMinYears: string;
  experienceMaxYears: string;
  salaryMin: string;
  salaryMax: string;
  salaryCurrency: string;
};

const emptyForm: FormState = {
  resumeText: "",
  preferredTitles: [],
  preferredLocations: [],
  preferredSkills: [],
  experienceMinYears: "",
  experienceMaxYears: "",
  salaryMin: "",
  salaryMax: "",
  salaryCurrency: "INR",
};

const optionalNumber = (value: string) =>
  value.trim() === "" ? null : Number(value);

function RequestError({ error }: { error: unknown }) {
  return (
    <div role="alert" className="rounded-lg border border-coral/40 bg-coral/5 p-4 text-sm text-coral">
      {errorSummary(error)}
      {isApiError(error) && error.requestId && (
        <p className="mt-1 font-mono text-xs text-muted-foreground">Request {error.requestId}</p>
      )}
    </div>
  );
}

export default function OnboardingPage() {
  const onboarding = useSWR<OnboardingState>("/api/onboarding");
  const { mutate } = useSWRConfig();
  const profile = onboarding.data?.memberProfile;
  const serverForm: FormState = profile
    ? {
        resumeText: profile.resumeText,
        preferredTitles: profile.preferredTitles,
        preferredLocations: profile.preferredLocations,
        preferredSkills: profile.preferredSkills,
        experienceMinYears: profile.experienceMinYears?.toString() ?? "",
        experienceMaxYears: profile.experienceMaxYears?.toString() ?? "",
        salaryMin: profile.salaryMin?.toString() ?? "",
        salaryMax: profile.salaryMax?.toString() ?? "",
        salaryCurrency: profile.salaryCurrency ?? "INR",
      }
    : emptyForm;
  const [formOverride, setFormOverride] = useState<FormState>();
  const form = formOverride ?? serverForm;
  const [busy, setBusy] = useState(false);
  const [requestError, setRequestError] = useState<unknown>();

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setFormOverride((current) => ({ ...(current ?? serverForm), [key]: value }));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setRequestError(undefined);
    const experienceMinYears = optionalNumber(form.experienceMinYears);
    const experienceMaxYears = optionalNumber(form.experienceMaxYears);
    const salaryMin = optionalNumber(form.salaryMin);
    const salaryMax = optionalNumber(form.salaryMax);
    if (!form.resumeText.trim()) {
      setRequestError(new Error("Profile or resume text is required."));
      return;
    }
    if (
      [experienceMinYears, experienceMaxYears, salaryMin, salaryMax].some(
        (value) => value !== null && (!Number.isFinite(value) || value < 0),
      )
    ) {
      setRequestError(new Error("Ranges must contain valid positive numbers."));
      return;
    }
    if (
      (experienceMinYears !== null && experienceMaxYears !== null && experienceMinYears > experienceMaxYears) ||
      (salaryMin !== null && salaryMax !== null && salaryMin > salaryMax)
    ) {
      setRequestError(new Error("A minimum value cannot exceed its maximum."));
      return;
    }

    setBusy(true);
    try {
      const result = await apiRequest<OnboardingResult>("/api/onboarding", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          experienceMinYears,
          experienceMaxYears,
          salaryMin,
          salaryMax,
          salaryCurrency: form.salaryCurrency.trim().toUpperCase() || null,
        }),
      });
      toast.success(result.replayed ? "Profile confirmed." : "Profile saved.", {
        description: result.message,
      });
      await mutate("/api/auth/session");
      window.location.assign("/dashboard");
    } catch (error) {
      setRequestError(error);
      toast.error(errorSummary(error));
    } finally {
      setBusy(false);
    }
  }

  if (onboarding.isLoading) {
    return <main className="mx-auto max-w-6xl space-y-5 p-6 lg:p-12"><Skeleton className="h-32 bg-raised" /><Skeleton className="h-[36rem] bg-raised" /></main>;
  }
  if (onboarding.error || !onboarding.data) {
    return <main className="mx-auto max-w-xl p-6 pt-24"><RequestError error={onboarding.error ?? new Error("Onboarding data is unavailable.")} /></main>;
  }

  return (
    <main className="mx-auto max-w-6xl px-5 py-8 sm:px-8 lg:py-12">
      <header className="grid gap-8 border-b border-border pb-9 lg:grid-cols-[1fr_.75fr] lg:items-end">
        <div>
          <p className="ops-label text-acid">Member setup / {onboarding.data.group.name}</p>
          <h1 className="mt-4 max-w-3xl text-5xl font-black uppercase tracking-[-0.055em] sm:text-7xl">
            Add your context.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-muted-foreground">
            The group model powers your results today. This profile is stored now so JEDI can personalize your ranking in v2.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <BrutalCard className="p-4">
            <BrainCircuit className="size-5 text-purple" />
            <p className="mt-5 ops-label text-muted-foreground">Active now</p>
            <p className="mt-2 text-sm font-semibold">Shared group profile</p>
          </BrutalCard>
          <BrutalCard className="p-4">
            <Database className="size-5 text-muted-foreground" />
            <p className="mt-5 ops-label text-muted-foreground">Saved for v2</p>
            <p className="mt-2 text-sm font-semibold">Your member profile</p>
          </BrutalCard>
        </div>
      </header>

      <div className="mt-8 grid gap-8 lg:grid-cols-[.7fr_1.3fr]">
        <aside className="space-y-4">
          <BrutalCard className="p-5">
            <p className="ops-label text-muted-foreground">Ranking profile</p>
            <h2 className="mt-3 text-xl font-semibold">{onboarding.data.sharedProfile ? "Configured" : "Not configured"}</h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{onboarding.data.sharedProfile?.resumePreview ?? "The group owner still needs to activate a profile."}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {onboarding.data.sharedProfile?.preferredTitles.slice(0, 4).map((title) => <span key={title} className="rounded-full border border-border px-3 py-1 text-xs">{title}</span>)}
            </div>
          </BrutalCard>
          <BrutalCard className="p-5">
            <p className="ops-label text-muted-foreground">Ranking model</p>
            <h2 className="mt-3 text-xl font-semibold">{onboarding.data.sharedModel?.name ?? "Not configured"}</h2>
            <p className="mt-2 font-mono text-xs text-muted-foreground">{onboarding.data.sharedModel?.featureSchemaVersion ?? "No feature contract pinned"}</p>
          </BrutalCard>
          <div className="flex gap-3 rounded-lg border border-acid/25 bg-acid/5 p-4 text-sm leading-6">
            <Check className="mt-0.5 size-4 shrink-0 text-acid" />
            Completing onboarding also adds your account email to the shared daily dispatch.
          </div>
        </aside>

        <form onSubmit={submit} className="space-y-7 rounded-xl border border-border bg-card p-5 sm:p-7">
          <div>
            <div className="flex items-center gap-3"><UserRound className="size-5 text-acid" /><h2 className="text-2xl font-semibold">Member profile</h2></div>
            <label htmlFor="resumeText" className="ops-label mt-7 block">Profile or resume content</label>
            <Textarea id="resumeText" value={form.resumeText} onChange={(event) => update("resumeText", event.target.value)} className="mt-2 min-h-48 border-border bg-background" placeholder="Paste your resume text or write a detailed professional summary." />
          </div>

          <TagField id="titles" label="Target titles" values={form.preferredTitles} suggestions={onboarding.data.suggestedTitles} placeholder="Type a title and press Enter" onChange={(values) => update("preferredTitles", values)} />
          <TagField id="locations" label="Preferred locations" values={form.preferredLocations} suggestions={onboarding.data.suggestedLocations} placeholder="Type a location and press Enter" onChange={(values) => update("preferredLocations", values)} />
          <TagField id="skills" label="Skills" values={form.preferredSkills} suggestions={onboarding.data.suggestedSkills} placeholder="Paste comma-separated skills" onChange={(values) => update("preferredSkills", values)} />

          <div className="grid gap-4 sm:grid-cols-2">
            <div><label htmlFor="experienceMin" className="ops-label">Experience minimum</label><Input id="experienceMin" type="number" min="0" step="0.5" value={form.experienceMinYears} onChange={(event) => update("experienceMinYears", event.target.value)} className="mt-2 min-h-11" /></div>
            <div><label htmlFor="experienceMax" className="ops-label">Experience maximum</label><Input id="experienceMax" type="number" min="0" step="0.5" value={form.experienceMaxYears} onChange={(event) => update("experienceMaxYears", event.target.value)} className="mt-2 min-h-11" /></div>
            <div><label htmlFor="salaryMin" className="ops-label">Salary minimum</label><Input id="salaryMin" type="number" min="0" value={form.salaryMin} onChange={(event) => update("salaryMin", event.target.value)} className="mt-2 min-h-11" /></div>
            <div><label htmlFor="salaryMax" className="ops-label">Salary maximum</label><Input id="salaryMax" type="number" min="0" value={form.salaryMax} onChange={(event) => update("salaryMax", event.target.value)} className="mt-2 min-h-11" /></div>
          </div>
          <div className="max-w-40"><label htmlFor="currency" className="ops-label">Currency</label><Input id="currency" maxLength={10} value={form.salaryCurrency} onChange={(event) => update("salaryCurrency", event.target.value.toUpperCase())} className="mt-2 min-h-11 uppercase" /></div>

          {Boolean(requestError) && <RequestError error={requestError} />}
          <Button type="submit" disabled={busy} className="min-h-12 w-full bg-foreground font-mono font-black uppercase text-background hover:bg-acid">
            {busy ? "Saving profile..." : "Finish onboarding"}{!busy && <ArrowRight className="size-4" />}
          </Button>
        </form>
      </div>
    </main>
  );
}
