"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { ArrowRight, Check, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import type { SkillGap } from "@/lib/learning";
import { errorSummary } from "@/lib/api";

export function SkillGapDetails({ gap }: { gap: SkillGap }) {
  if (!gap.hasResume)
    return (
      <div className="rounded-lg border border-purple/30 bg-purple/5 p-5">
        <p className="text-sm leading-6">
          Add a resume to compare this role with your skills.
        </p>
        <Link
          href="/onboarding"
          className="mt-3 inline-flex min-h-10 items-center gap-2 text-sm text-acid"
        >
          Upload your resume <ArrowRight className="size-4" />
        </Link>
      </div>
    );
  return (
    <div className="space-y-6">
      <section>
        <h3 className="ops-label text-acid">
          Matching skills · {gap.matched.length}
        </h3>
        <p className="mt-2 text-xs text-muted-foreground">
          Inferred matches are tentative. Review your resume evidence to correct
          them.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {gap.matched.map((item) => (
            <span
              title={item.evidence}
              key={item.skill}
              className="inline-flex items-center gap-2 rounded-full border border-acid/30 bg-acid/5 px-3 py-2 text-xs"
            >
              <Check className="size-3 text-acid" />
              {item.skill}
              <span className="text-muted-foreground">{item.source}</span>
            </span>
          ))}
        </div>
        {!gap.matched.length && (
          <p className="mt-3 text-sm text-muted-foreground">
            No matching skills found in your saved resume.
          </p>
        )}
      </section>
      <section>
        <h3 className="ops-label text-purple">
          Skills to prepare · {gap.missing.length}
        </h3>
        <div className="mt-3 space-y-3">
          {gap.missing.map((item) => (
            <div
              key={item.skill}
              className="rounded-lg border border-border bg-card p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <strong className="text-sm">{item.skill}</strong>
                <span className="ops-label text-muted-foreground">
                  {item.requirement === "uncertain"
                    ? "Confirm requirement"
                    : item.requirement}
                </span>
              </div>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                {item.evidence}
              </p>
              {item.topicIds.length ? (
                <Link
                  className="mt-3 inline-flex min-h-9 items-center gap-2 text-sm text-acid"
                  href={`/learning?jobId=${encodeURIComponent(gap.jobId)}`}
                >
                  Open learning path <ArrowRight className="size-4" />
                </Link>
              ) : (
                <p className="mt-3 font-mono text-[11px] uppercase text-muted-foreground">
                  Question bank unavailable
                </p>
              )}
            </div>
          ))}
        </div>
        {!gap.missing.length && (
          <p className="mt-3 text-sm text-acid">
            Your resume covers the recognized skills for this role.
          </p>
        )}
      </section>
      <Link
        href="/onboarding"
        className="inline-flex min-h-9 items-center text-xs text-muted-foreground underline underline-offset-4"
      >
        Review your resume evidence
      </Link>
    </div>
  );
}

export function SkillGapButton({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false);
  const gap = useSWR<SkillGap>(
    open ? `/api/jobs/${encodeURIComponent(jobId)}/skill-gap` : null,
    { revalidateOnMount: true },
  );
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Target />
        Compare skills
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Prepare for this role</DialogTitle>
            <DialogDescription>
              Compare job requirements against your personal resume. Shared
              ranking scores stay independent.
            </DialogDescription>
          </DialogHeader>
          {gap.isLoading && (
            <p className="text-sm text-muted-foreground">Comparing skills…</p>
          )}
          {gap.error && (
            <div role="alert" className="text-sm text-coral">
              {errorSummary(gap.error)}{" "}
              <Button variant="outline" onClick={() => void gap.mutate()}>
                Retry
              </Button>
            </div>
          )}
          {gap.data && <SkillGapDetails gap={gap.data} />}
        </DialogContent>
      </Dialog>
    </>
  );
}
