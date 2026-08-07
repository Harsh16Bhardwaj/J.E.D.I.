"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  BellRing,
  BrainCircuit,
  BriefcaseBusiness,
  Check,
  ChevronRight,
  CircleDot,
  Database,
  FileCheck2,
  Flame,
  Gauge,
  GitMerge,
  Layers3,
  LockKeyhole,
  Mail,
  Radar,
  ShieldCheck,
  Sparkles,
  Target,
  Upload,
  UserRoundCheck,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";

import { RouteHeader } from "@/components/route-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  hasCompletedTutorial,
  markTutorialCompleteInBrowser,
} from "@/lib/tutorial-state";

type Accent = "acid" | "purple" | "coral";

type JourneyStep = {
  number: string;
  title: string;
  summary: string;
  icon: LucideIcon;
  accent: Accent;
};

const accentText: Record<Accent, string> = {
  acid: "text-acid",
  purple: "text-purple",
  coral: "text-coral",
};

const accentBorder: Record<Accent, string> = {
  acid: "border-acid/30",
  purple: "border-purple/30",
  coral: "border-coral/30",
};

const journey: JourneyStep[] = [
  {
    number: "01",
    title: "Collect",
    summary: "A daily collector produces one schema-safe job file.",
    icon: Radar,
    accent: "acid",
  },
  {
    number: "02",
    title: "Import",
    summary: "JEDI validates, cleans, and removes duplicate jobs.",
    icon: Upload,
    accent: "purple",
  },
  {
    number: "03",
    title: "Normalize",
    summary: "Every job becomes a profile-pinned model payload.",
    icon: GitMerge,
    accent: "acid",
  },
  {
    number: "04",
    title: "Rank",
    summary: "The embedded model scores and persists the complete batch.",
    icon: BrainCircuit,
    accent: "purple",
  },
  {
    number: "05",
    title: "Notify",
    summary: "Each member receives an auditable ranked-job digest.",
    icon: BellRing,
    accent: "coral",
  },
  {
    number: "06",
    title: "Act",
    summary: "Review jobs and manage a private application pipeline.",
    icon: BriefcaseBusiness,
    accent: "acid",
  },
];

const destinations = [
  {
    href: "/dashboard",
    eyebrow: "Start here",
    title: "Daily Feed",
    description: "The strongest ranked jobs, pipeline totals, and the next actions that need attention.",
    icon: Gauge,
  },
  {
    href: "/jobs",
    eyebrow: "Review",
    title: "Jobs",
    description: "Search the shared job pool, inspect model results, bookmark work, and begin an application.",
    icon: Target,
  },
  {
    href: "/applications",
    eyebrow: "Private",
    title: "Applications",
    description: "Move opportunities through stages and track deadlines, notes, and interview rounds.",
    icon: LockKeyhole,
  },
  {
    href: "/batches",
    eyebrow: "Operations",
    title: "Batches",
    description: "Import daily JSON, inspect validation, normalize jobs, run rankings, and audit history.",
    icon: Layers3,
  },
  {
    href: "/settings/email",
    eyebrow: "Delivery",
    title: "Email",
    description: "Manage recipients and inspect every queued, sent, failed, blocked, or cancelled event.",
    icon: Mail,
  },
  {
    href: "/settings/models",
    eyebrow: "Owner control",
    title: "Models",
    description: "Register and activate immutable bundles, warm the runtime, and review deployment evidence.",
    icon: Activity,
  },
];

function JourneyCard({ step }: { step: JourneyStep }) {
  const Icon = step.icon;
  return (
    <li className="relative min-w-0 bg-card p-4 sm:p-5">
      <div className="flex items-start justify-between gap-4">
        <span className={cn("font-mono text-xs font-black", accentText[step.accent])}>{step.number}</span>
        <Icon className={cn("size-5", accentText[step.accent])} aria-hidden="true" />
      </div>
      <h3 className="mt-8 text-lg font-black uppercase tracking-tight">{step.title}</h3>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">{step.summary}</p>
    </li>
  );
}

function FlowArrow() {
  return (
    <div className="flex items-center justify-center py-2 text-muted-foreground md:py-0" aria-hidden="true">
      <ArrowRight className="size-5 rotate-90 md:rotate-0" />
    </div>
  );
}

export default function TutorialPage() {
  const [complete, setComplete] = useState(false);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setComplete(hasCompletedTutorial(window.localStorage));
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  function markComplete() {
    markTutorialCompleteInBrowser();
    setComplete(true);
    toast.success("Tutorial marked as complete.");
  }

  return (
    <div className="mx-auto max-w-7xl space-y-14 pb-10">
      <RouteHeader
        eyebrow="Product field guide"
        title="How JEDI turns job noise into action"
        path="/tutorial"
        description="Follow a job from daily collection to a ranked recommendation, a personalized email, and your private application board."
      />

      <section className="relative overflow-hidden border border-border bg-card" aria-labelledby="system-map-title">
        <div className="absolute inset-y-0 right-0 hidden w-1/3 bg-[radial-gradient(circle_at_center,hsl(var(--acid)/0.12),transparent_68%)] lg:block" />
        <div className="relative grid gap-8 p-6 sm:p-8 lg:grid-cols-[1.3fr_0.7fr] lg:p-10">
          <div>
            <p className="ops-label text-acid">One connected system</p>
            <h2 id="system-map-title" className="mt-4 max-w-3xl text-3xl font-black uppercase leading-[0.95] tracking-[-0.045em] sm:text-5xl">
              Discover broadly.<br />Decide with evidence.<br />Track every move.
            </h2>
            <p className="mt-6 max-w-2xl text-sm leading-7 text-muted-foreground">
              Collection finds relevant opportunities. JEDI owns validation, feature preparation, model inference, ranking history, delivery, and the application workflow. Every important transition is persisted so the result can be inspected instead of trusted blindly.
            </p>
          </div>
          <div className="grid gap-px self-end border border-border bg-border sm:grid-cols-3 lg:grid-cols-1">
            {[
              ["30 days", "Maximum import age"],
              ["2 outputs", "Preference + apply probability"],
              ["Private", "Member application activity"],
            ].map(([value, label]) => (
              <div key={label} className="bg-background p-4">
                <p className="text-2xl font-black uppercase tracking-tight">{value}</p>
                <p className="mt-1 text-xs text-muted-foreground">{label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="space-y-6" aria-labelledby="journey-title">
        <div className="flex flex-col justify-between gap-4 border-b border-border pb-5 sm:flex-row sm:items-end">
          <div>
            <p className="ops-label text-purple">The daily journey</p>
            <h2 id="journey-title" className="mt-2 text-3xl font-black uppercase tracking-tight">Six stages, one durable trail</h2>
          </div>
          <p className="max-w-lg text-sm leading-6 text-muted-foreground">The collector supplies candidates. The JEDI site takes responsibility from import onward.</p>
        </div>
        <ol className="grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-2 lg:grid-cols-6">
          {journey.map((step) => <JourneyCard key={step.number} step={step} />)}
        </ol>
      </section>

      <section className="space-y-8" aria-labelledby="intake-title">
        <div className="grid gap-8 lg:grid-cols-[0.7fr_1.3fr]">
          <div>
            <p className="ops-label text-acid">01 / Intake and cleanup</p>
            <h2 id="intake-title" className="mt-3 text-3xl font-black uppercase tracking-tight">A clean batch enters the system</h2>
            <p className="mt-4 text-sm leading-7 text-muted-foreground">
              Upload the dated JSON created by the scheduled collector. JEDI rejects malformed envelopes and stale postings, canonicalizes job data, and checks both exact and strong multi-signal duplicates before saving anything.
            </p>
            <Link href="/batches?import=1" className={buttonVariants({ className: "mt-6 min-h-11" })}>
              Open batch import <ChevronRight />
            </Link>
          </div>
          <div className="grid items-stretch md:grid-cols-[1fr_auto_1fr_auto_1fr]">
            <div className="border border-border bg-card p-5">
              <FileCheck2 className="size-6 text-acid" aria-hidden="true" />
              <p className="mt-8 ops-label text-muted-foreground">Validate</p>
              <h3 className="mt-2 font-black uppercase">Contract + freshness</h3>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">The import envelope, required fields, dates, and URLs must pass backend rules.</p>
            </div>
            <FlowArrow />
            <div className="border border-border bg-card p-5">
              <Sparkles className="size-6 text-purple" aria-hidden="true" />
              <p className="mt-8 ops-label text-muted-foreground">Clean</p>
              <h3 className="mt-2 font-black uppercase">Canonical values</h3>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">Whitespace, choices, skills, company identity, and application URLs are normalized.</p>
            </div>
            <FlowArrow />
            <div className="border border-border bg-card p-5">
              <GitMerge className="size-6 text-coral" aria-hidden="true" />
              <p className="mt-8 ops-label text-muted-foreground">Deduplicate</p>
              <h3 className="mt-2 font-black uppercase">No review queue</h3>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">URL, stable content keys, and matching job signals remove duplicates automatically.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-border py-10" aria-labelledby="model-title">
        <div className="grid gap-8 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="ops-label text-purple">02 / Preparation and inference</p>
            <h2 id="model-title" className="mt-3 text-3xl font-black uppercase tracking-tight">What the model actually does</h2>
            <p className="mt-4 text-sm leading-7 text-muted-foreground">
              Normalization and ranking are separate, explicit operations. This keeps the active profile, prepared features, model artifact, and every prediction version auditable.
            </p>
          </div>
          <div className="space-y-3">
            <article className={cn("grid gap-5 border bg-card p-5 sm:grid-cols-[auto_1fr]", accentBorder.acid)}>
              <div className="flex size-12 items-center justify-center border border-acid/30 bg-acid/10"><GitMerge className="size-5 text-acid" /></div>
              <div><p className="ops-label text-acid">Normalize</p><h3 className="mt-2 text-xl font-black uppercase">Build prepared-job-v2</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">The active immutable profile is combined with each job to create a versioned feature payload. Replaying the same profile and batch is idempotent.</p></div>
            </article>
            <article className={cn("grid gap-5 border bg-card p-5 sm:grid-cols-[auto_1fr]", accentBorder.coral)}>
              <div className="flex size-12 items-center justify-center border border-coral/30 bg-coral/10"><Flame className="size-5 text-coral" /></div>
              <div><p className="ops-label text-coral">Warm up</p><h3 className="mt-2 text-xl font-black uppercase">Load and verify the bundle</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">Warmup loads the embedded artifact once, verifies its manifest and hashes, and runs a golden smoke test. Ranking can then avoid a cold model load.</p></div>
            </article>
            <article className={cn("grid gap-5 border bg-card p-5 sm:grid-cols-[auto_1fr]", accentBorder.purple)}>
              <div className="flex size-12 items-center justify-center border border-purple/30 bg-purple/10"><BrainCircuit className="size-5 text-purple" /></div>
              <div><p className="ops-label text-purple">Rank</p><h3 className="mt-2 text-xl font-black uppercase">Score the complete batch</h3><p className="mt-2 text-sm leading-6 text-muted-foreground">The run pins the active profile and model, scores every prepared job, records timings and cold-start state, then saves all predictions atomically.</p></div>
            </article>
          </div>
        </div>

        <div className="mt-8 grid gap-px overflow-hidden border border-border bg-border lg:grid-cols-[1fr_auto_1fr_auto_1fr]">
          <div className="bg-background p-6">
            <p className="ops-label text-muted-foreground">Fit components</p>
            <p className="mt-3 text-lg font-black uppercase">Role · skills · experience · location · salary</p>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">Component models explain where the job aligns with the active profile.</p>
          </div>
          <FlowArrow />
          <div className="bg-background p-6">
            <p className="ops-label text-purple">JEDI preference score</p>
            <p className="mt-3 text-lg font-black uppercase">Controls ordering</p>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">The weighted 0–100 score determines which jobs rise to the top.</p>
          </div>
          <FlowArrow />
          <div className="bg-background p-6">
            <p className="ops-label text-coral">Apply probability</p>
            <p className="mt-3 text-lg font-black uppercase">Acts as a guardrail</p>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">A separate classifier supports the apply recommendation; it does not replace the ranking score.</p>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/settings/profile" className={buttonVariants({ variant: "outline", className: "min-h-11" })}>Shared profile <ChevronRight /></Link>
          <Link href="/settings/models" className={buttonVariants({ variant: "outline", className: "min-h-11" })}>Model registry <ChevronRight /></Link>
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-2" aria-label="Delivery and application workflow">
        <article className="border border-border bg-card p-6 sm:p-8">
          <div className="flex items-start justify-between gap-4"><div><p className="ops-label text-coral">03 / Personalized delivery</p><h2 className="mt-3 text-2xl font-black uppercase">Ranking creates the mail event</h2></div><Mail className="size-7 text-coral" /></div>
          <p className="mt-5 text-sm leading-7 text-muted-foreground">After a successful ranking, JEDI creates one auditable event for each group member. A personalized top-job snapshot is rendered at send time, while the delivery ledger preserves retries and failures.</p>
          <ol className="mt-6 space-y-3">
            {[
              ["UNTOUCHED", "Eligible and waiting for dispatch"],
              ["SENDING → SENT", "Claimed safely and accepted by the mail transport"],
              ["FAILED / BLOCKED", "Retryable failure or missing member setup"],
              ["CANCELLED", "Paused recipient or an older event superseded by reranking"],
            ].map(([status, meaning]) => <li key={status} className="flex gap-3 border-t border-border pt-3"><CircleDot className="mt-0.5 size-4 shrink-0 text-coral" /><div><strong className="font-mono text-xs">{status}</strong><p className="mt-1 text-xs text-muted-foreground">{meaning}</p></div></li>)}
          </ol>
          <Link href="/settings/email" className={buttonVariants({ variant: "outline", className: "mt-6 min-h-11" })}>Open email control <ChevronRight /></Link>
        </article>

        <article className="border border-border bg-card p-6 sm:p-8">
          <div className="flex items-start justify-between gap-4"><div><p className="ops-label text-acid">04 / Private execution</p><h2 className="mt-3 text-2xl font-black uppercase">Turn a ranked job into a plan</h2></div><UserRoundCheck className="size-7 text-acid" /></div>
          <p className="mt-5 text-sm leading-7 text-muted-foreground">Jobs and rankings are shared with the group. Your view state, bookmark, notes, application plan, status history, deadlines, and milestones belong only to your member account.</p>
          <div className="mt-6 flex flex-wrap items-center gap-2" aria-label="Application stages">
            {["Preparing", "Applied", "Screening", "Assessment", "Interview", "Offer", "Outcome"].map((stage, index) => (
              <div key={stage} className="flex items-center gap-2"><span className="border border-border bg-background px-2.5 py-2 font-mono text-[10px] font-bold uppercase">{stage}</span>{index < 6 && <ArrowRight className="size-3 text-muted-foreground" />}</div>
            ))}
          </div>
          <div className="mt-6 border border-acid/20 bg-acid/5 p-4"><div className="flex gap-3"><ShieldCheck className="mt-0.5 size-5 shrink-0 text-acid" /><div><strong className="text-sm">Private by construction</strong><p className="mt-1 text-xs leading-5 text-muted-foreground">Status changes append permanent history events; application plan edits use version checks to prevent silent overwrites.</p></div></div></div>
          <Link href="/applications" className={buttonVariants({ className: "mt-6 min-h-11" })}>Open your applications <ChevronRight /></Link>
        </article>
      </section>

      <section className="space-y-6" aria-labelledby="site-map-title">
        <div className="border-b border-border pb-5"><p className="ops-label text-acid">Site map</p><h2 id="site-map-title" className="mt-2 text-3xl font-black uppercase tracking-tight">Where to do each job</h2></div>
        <div className="grid gap-px overflow-hidden border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {destinations.map((item) => {
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} className="group bg-card p-5 transition-colors hover:bg-raised">
                <div className="flex items-start justify-between gap-4"><Icon className="size-5 text-acid" /><ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-foreground" /></div>
                <p className="mt-8 ops-label text-muted-foreground">{item.eyebrow}</p>
                <h3 className="mt-2 text-xl font-black uppercase">{item.title}</h3>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">{item.description}</p>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="border-t border-border pt-8">
        <div className="flex flex-col items-start justify-between gap-5 border border-border bg-card p-5 sm:flex-row sm:items-center sm:p-6">
          <div><p className="ops-label text-purple">Field guide complete</p><h2 className="mt-2 text-xl font-black uppercase">You know the full JEDI loop</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Mark this tutorial complete when you understand the path from batch import to private application tracking. It stays available in the sidebar.</p></div>
          <Button type="button" className="min-h-11 shrink-0 bg-foreground text-background hover:bg-acid" disabled={complete} onClick={markComplete}>
            {complete ? <Check className="size-4" /> : <Database className="size-4" />}{complete ? "Tutorial complete" : "Mark tutorial complete"}
          </Button>
        </div>
      </section>
    </div>
  );
}
