"use client";

import { useState } from "react";
import { ArrowRight, BrainCircuit, Check, Database, UserRound } from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import type { ResumeEvidence } from "@/lib/learning";
import { ResumeUpload } from "@/components/resume-upload";
import { BrutalCard } from "@/components/brutal-card";
import { TagField } from "@/components/tag-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  apiRequest,
  errorSummary,
  isApiError,
  type OnboardingResult,
  type OnboardingState,
} from "@/lib/api";
import {
  type OnboardingFieldErrors,
  type OnboardingFormState,
  experienceRanges,
  validateOnboardingForm,
} from "@/lib/onboarding-validation";

const emptyForm: OnboardingFormState = {
  preferredTitles: [],
  preferredLocations: [],
  preferredSkills: [],
  experienceRange: "",
  salaryMinLpa: "",
};

function storedExperienceRange(minimum: number | null, maximum: number | null) {
  return Object.entries(experienceRanges).find(
    ([, range]) => range.minimum === minimum && range.maximum === maximum,
  )?.[0] ?? "";
}

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

function ValidationSummary({ errors }: { errors: OnboardingFieldErrors }) {
  const messages = [...new Set(Object.values(errors))];
  if (!messages.length) return null;
  return (
    <div role="alert" className="rounded-lg border border-coral/40 bg-coral/5 p-4 text-sm text-coral">
      <p className="font-semibold">Complete all required fields before finishing onboarding.</p>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {messages.map((message) => <li key={message}>{message}</li>)}
      </ul>
    </div>
  );
}

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? <p id={id} className="mt-2 text-xs text-coral">{message}</p> : null;
}

export default function OnboardingPage() {
  const onboarding = useSWR<OnboardingState>("/api/onboarding");
  const resume = useSWR<ResumeEvidence | null>("/api/resume");
  const resumeHasSkills = Boolean(resume.data?.explicitSkills.length);
  const resumeHasExperience = resume.data?.experienceYears != null;
  const { mutate } = useSWRConfig();
  const profile = onboarding.data?.memberProfile;
  const serverForm: OnboardingFormState = profile
    ? {
        preferredTitles: profile.preferredTitles,
        preferredLocations: profile.preferredLocations,
        preferredSkills: profile.preferredSkills,
        experienceRange: storedExperienceRange(
          profile.experienceMinYears,
          profile.experienceMaxYears,
        ),
        salaryMinLpa:
          profile.salaryMin === null ? "" : (profile.salaryMin / 100_000).toString(),
      }
    : emptyForm;
  const [formOverride, setFormOverride] = useState<OnboardingFormState>();
  const form = formOverride ?? serverForm;
  const [busy, setBusy] = useState(false);
  const [resumePending, setResumePending] = useState(false);
  const [requestError, setRequestError] = useState<unknown>();
  const [fieldErrors, setFieldErrors] = useState<OnboardingFieldErrors>({});

  function update<K extends keyof OnboardingFormState>(key: K, value: OnboardingFormState[K]) {
    setFormOverride((current) => ({ ...(current ?? serverForm), [key]: value }));
    setFieldErrors((current) => {
      const relatedKeys: Array<keyof OnboardingFormState> = [key];
      if (!relatedKeys.some((relatedKey) => current[relatedKey])) return current;
      const next = { ...current };
      for (const relatedKey of relatedKeys) delete next[relatedKey];
      return next;
    });
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || resumePending) return;
    setRequestError(undefined);
    const validation = validateOnboardingForm(form, resume.data);
    setFieldErrors(validation.errors);
    if (!validation.values) {
      toast.error("Complete all required onboarding fields.");
      return;
    }

    setBusy(true);
    try {
      const result = await apiRequest<OnboardingResult>("/api/onboarding", {
        method: "POST",
        body: JSON.stringify(validation.values),
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

        <form noValidate onSubmit={submit} className="space-y-7 rounded-xl border border-border bg-card p-5 sm:p-7">
          <div>
            <div className="flex items-center gap-3"><UserRound className="size-5 text-acid" /><h2 className="text-2xl font-semibold">Member profile</h2></div>
            <p className="mt-2 text-xs text-muted-foreground">Review your resume once, then set your job preferences. You can enter skills and experience manually if you skip the resume.</p>
          </div>

          <ResumeUpload onPendingChange={setResumePending} />

          <TagField id="titles" label="Target titles *" values={form.preferredTitles} suggestions={onboarding.data.suggestedTitles} placeholder="Type a title and press Enter" error={fieldErrors.preferredTitles} onChange={(values) => update("preferredTitles", values)} />
          <TagField id="locations" label="Preferred locations *" values={form.preferredLocations} suggestions={onboarding.data.suggestedLocations} placeholder="Type a location and press Enter" error={fieldErrors.preferredLocations} onChange={(values) => update("preferredLocations", values)} />
          {!resumeHasSkills && !resumePending && <TagField id="skills" label="Skills *" values={form.preferredSkills} suggestions={onboarding.data.suggestedSkills} placeholder="Paste comma-separated skills" error={fieldErrors.preferredSkills} onChange={(values) => update("preferredSkills", values)} />}

          <div className="grid gap-4 sm:grid-cols-2">
            {!resumeHasExperience && !resumePending && <div>
              <label htmlFor="experienceRange" className="ops-label">Experience *</label>
              <select
                id="experienceRange"
                required
                aria-invalid={Boolean(fieldErrors.experienceRange)}
                aria-describedby={fieldErrors.experienceRange ? "experienceRange-error" : undefined}
                value={form.experienceRange}
                onChange={(event) => update("experienceRange", event.target.value)}
                className="mt-2 min-h-11 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-coral/60"
              >
                <option value="">Select experience</option>
                {Object.entries(experienceRanges).map(([value, range]) => (
                  <option key={value} value={value}>{range.label}</option>
                ))}
              </select>
              <FieldError id="experienceRange-error" message={fieldErrors.experienceRange} />
            </div>}
            <div>
              <label htmlFor="salaryMinLpa" className="ops-label">Minimum salary (LPA) *</label>
              <Input id="salaryMinLpa" required aria-invalid={Boolean(fieldErrors.salaryMinLpa)} aria-describedby={fieldErrors.salaryMinLpa ? "salaryMinLpa-error" : undefined} type="number" min="0" step="0.1" value={form.salaryMinLpa} onChange={(event) => update("salaryMinLpa", event.target.value)} className="mt-2 min-h-11 aria-invalid:border-coral/60" placeholder="e.g. 8" />
              <FieldError id="salaryMinLpa-error" message={fieldErrors.salaryMinLpa} />
            </div>
          </div>

          {resumePending && <p role="status" className="text-xs text-purple">Save or discard your resume changes before finishing onboarding.</p>}
          <ValidationSummary errors={fieldErrors} />
          {Boolean(requestError) && <RequestError error={requestError} />}
          <Button type="submit" disabled={busy || resumePending || resume.isLoading || Boolean(resume.error)} className="min-h-12 w-full bg-foreground font-mono font-black uppercase text-background hover:bg-acid">
            {busy ? "Saving profile..." : "Finish onboarding"}{!busy && <ArrowRight className="size-4" />}
          </Button>
        </form>
      </div>
    </main>
  );
}
