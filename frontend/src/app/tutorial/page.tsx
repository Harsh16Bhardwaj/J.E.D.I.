"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Copy,
  ExternalLink,
  FileJson,
  Flag,
  Info,
  Search,
  Upload,
} from "lucide-react";
import { toast } from "sonner";

import { RouteHeader } from "@/components/route-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  buildJobSearchPrompt,
  isJobSearchComplete,
  type JobSearchCriteria,
} from "@/lib/tutorial-prompt";
import {
  hasCompletedTutorial,
  markTutorialCompleteInBrowser,
} from "@/lib/tutorial-state";

const initialCriteria: JobSearchCriteria = {
  postedDays: 2,
  salaryMinimum: "",
  preferredRoles: "",
  experienceYears: "",
  companyType: "ALL",
  locations: "",
};

const companyTypes = [
  { value: "STARTUP", label: "Startup" },
  { value: "MNC", label: "MNC" },
  { value: "PRODUCT_GIANTS", label: "Product giants" },
  { value: "ALL", label: "All company types" },
] as const;

export default function TutorialPage() {
  const [criteria, setCriteria] = useState(initialCriteria);
  const [complete, setComplete] = useState(false);
  const prompt = useMemo(() => buildJobSearchPrompt(criteria), [criteria]);
  const readyToCopy = isJobSearchComplete(criteria);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setComplete(hasCompletedTutorial(window.localStorage));
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  function update<K extends keyof JobSearchCriteria>(
    key: K,
    value: JobSearchCriteria[K],
  ) {
    setCriteria((current) => ({ ...current, [key]: value }));
  }

  async function copyPrompt() {
    if (!readyToCopy) return;
    try {
      await navigator.clipboard.writeText(prompt);
      toast.success("Prompt copied.", {
        description: "Paste it into an LLM with internet search enabled.",
      });
    } catch {
      toast.error("The prompt could not be copied. Select it manually instead.");
    }
  }

  function markComplete() {
    markTutorialCompleteInBrowser();
    setComplete(true);
    toast.success("Tutorial marked as complete.");
  }

  return (
    <div className="mx-auto max-w-6xl space-y-10">
      <RouteHeader
        eyebrow="Getting started"
        title="Using JEDI today"
        path="/tutorial"
        description="Create a job-search prompt, ask an LLM to research current openings, and import the resulting JSON as a JEDI batch."
      />

      <section className="border border-border bg-card p-5 sm:p-6">
        <div className="flex gap-3">
          <Info className="mt-0.5 size-5 shrink-0 text-acid" aria-hidden="true" />
          <div>
            <h2 className="font-semibold">What this workflow does</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              JEDI does not run a large scraper. You provide a few requirements, an LLM with internet search finds current jobs, and JEDI validates and deduplicates the returned JSON before creating a batch.
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-6" aria-labelledby="step-one-title">
        <div className="border-b border-border pb-4">
          <p className="ops-label text-acid">Step 1</p>
          <h2 id="step-one-title" className="mt-2 text-3xl font-semibold">Enter your job requirements</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            These values are inserted into the research prompt in Step 2.
          </p>
        </div>

        <div className="grid gap-5 border border-border bg-card p-5 sm:p-6 md:grid-cols-2">
          <label className="space-y-2">
            <span className="text-sm font-medium">Posted within the last number of days</span>
            <Input
              type="number"
              min={1}
              max={30}
              value={criteria.postedDays}
              onChange={(event) => update("postedDays", Math.min(30, Math.max(1, Number(event.target.value) || 1)))}
            />
            <span className="block text-xs text-muted-foreground">Default: 2 days. Maximum: 30 days.</span>
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium">Minimum annual salary in INR</span>
            <Input
              type="number"
              min={0}
              step={100000}
              placeholder="For example: 1200000"
              value={criteria.salaryMinimum}
              onChange={(event) => update("salaryMinimum", event.target.value)}
            />
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium">Preferred roles</span>
            <Input
              placeholder="Backend Engineer, Python Engineer"
              value={criteria.preferredRoles}
              onChange={(event) => update("preferredRoles", event.target.value)}
            />
            <span className="block text-xs text-muted-foreground">Separate multiple roles with commas.</span>
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium">Experience in years</span>
            <Input
              type="number"
              min={0}
              max={80}
              step={0.5}
              placeholder="For example: 2"
              value={criteria.experienceYears}
              onChange={(event) => update("experienceYears", event.target.value)}
            />
            <span className="block text-xs text-muted-foreground">The prompt also searches one year below and above this value.</span>
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium">Company type</span>
            <select
              className="flex min-h-10 w-full border border-input bg-background px-3 py-2 text-sm"
              value={criteria.companyType}
              onChange={(event) => update("companyType", event.target.value as JobSearchCriteria["companyType"])}
            >
              {companyTypes.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
            </select>
          </label>

          <label className="space-y-2">
            <span className="text-sm font-medium">Preferred locations</span>
            <Input
              placeholder="Bengaluru, Hyderabad, Remote"
              value={criteria.locations}
              onChange={(event) => update("locations", event.target.value)}
            />
            <span className="block text-xs text-muted-foreground">Separate multiple locations with commas.</span>
          </label>
        </div>
      </section>

      <section className="space-y-6" aria-labelledby="step-two-title">
        <div className="border-b border-border pb-4">
          <p className="ops-label text-purple">Step 2</p>
          <h2 id="step-two-title" className="mt-2 text-3xl font-semibold">Give this prompt to your preferred LLM</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Turn on internet search or web browsing before submitting it. The prompt updates immediately when you change a field in Step 1.
          </p>
        </div>

        {!readyToCopy && (
          <div role="status" className="border border-coral/30 bg-coral/5 p-4 text-sm text-coral">
            Enter a minimum salary, at least one role, your experience, and at least one location before copying the prompt.
          </div>
        )}

        <div className="border border-border bg-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
            <div className="flex items-center gap-2">
              <Search className="size-4 text-purple" aria-hidden="true" />
              <span className="font-mono text-xs font-bold uppercase tracking-wider">Generated research prompt</span>
            </div>
            <Button
              type="button"
              className="min-h-10 bg-foreground text-background hover:bg-acid"
              disabled={!readyToCopy}
              onClick={() => void copyPrompt()}
            >
              <Copy className="size-4" /> Copy prompt
            </Button>
          </div>
          <Textarea
            readOnly
            spellCheck={false}
            value={prompt}
            aria-label="Generated job research prompt"
            className="min-h-[34rem] resize-y border-0 bg-background p-5 font-mono text-xs leading-5 focus-visible:ring-0"
          />
        </div>
      </section>

      <section className="space-y-6" aria-labelledby="step-three-title">
        <div className="border-b border-border pb-4">
          <p className="ops-label text-acid">Step 3</p>
          <h2 id="step-three-title" className="mt-2 text-3xl font-semibold">Import the JSON into JEDI</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            The LLM should generate a JSON file. You can upload that file or paste its contents into the batch import screen.
          </p>
        </div>

        <ol className="grid gap-px overflow-hidden border border-border bg-border md:grid-cols-3">
          <li className="bg-card p-5">
            <FileJson className="size-5 text-acid" aria-hidden="true" />
            <strong className="mt-5 block">1. Check the output</strong>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">It must be one JSON object with an externalBatchId, generatedAt, and a non-empty jobs array.</p>
          </li>
          <li className="bg-card p-5">
            <Upload className="size-5 text-acid" aria-hidden="true" />
            <strong className="mt-5 block">2. Open batch import</strong>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Choose the JSON file from your computer, or paste the complete JSON into the editor.</p>
          </li>
          <li className="bg-card p-5">
            <Check className="size-5 text-acid" aria-hidden="true" />
            <strong className="mt-5 block">3. Import and review</strong>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">JEDI validates every job, reports invalid rows, removes duplicates, and creates the retained batch.</p>
          </li>
        </ol>

        <Link
          href="/batches?import=1"
          className="inline-flex min-h-11 items-center gap-2 bg-acid px-4 font-mono text-xs font-bold uppercase text-background hover:bg-foreground"
        >
          Open batch import <ExternalLink className="size-4" aria-hidden="true" />
        </Link>
      </section>

      <section className="border-t border-border pt-8">
        <div className="flex flex-col items-start justify-between gap-5 border border-border bg-card p-5 sm:flex-row sm:items-center sm:p-6">
          <div>
            <h2 className="text-xl font-semibold">Tutorial completion</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Mark the tutorial complete after you understand how to generate and import a batch. The Tutorial page remains available in the sidebar.
            </p>
          </div>
          <Button
            type="button"
            className="min-h-11 shrink-0 bg-foreground text-background hover:bg-acid"
            disabled={complete}
            onClick={markComplete}
          >
            {complete ? <Check className="size-4" /> : <Flag className="size-4" />}
            {complete ? "Tutorial complete" : "Mark tutorial complete"}
          </Button>
        </div>
      </section>
    </div>
  );
}
