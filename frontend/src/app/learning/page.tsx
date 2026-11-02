"use client";

import { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { ArrowRight, BookOpen, Clock3, Target } from "lucide-react";
import { BrutalCard } from "@/components/brutal-card";
import { RouteHeader } from "@/components/route-header";
import { SkillGapDetails } from "@/components/skill-gap";
import { LearningSprint } from "@/components/learning-sprint";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { apiRequest, errorSummary, type JobPage } from "@/lib/api";
import {
  sprintSettings,
  type LearningTopic,
  type SkillGap,
  type SprintAttempt,
} from "@/lib/learning";

function TopicCard({
  topic,
  jobId,
  label,
  onStart,
}: {
  topic: LearningTopic;
  jobId?: string;
  label: string;
  onStart: (attempt: SprintAttempt) => void;
}) {
  const [count, setCount] = useState(Math.min(topic.questionCount, 10));
  const [seconds, setSeconds] = useState(300);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  async function start() {
    if (!sprintSettings(count, seconds, topic.questionCount) || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      onStart(
        await apiRequest<SprintAttempt>("/api/learning/attempts", {
          method: "POST",
          body: JSON.stringify({
            topicId: topic.topicId,
            questionCount: count,
            durationSeconds: seconds,
            jobId: jobId ?? null,
          }),
        }),
      );
    } catch (cause) {
      setError(errorSummary(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <BrutalCard className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <BookOpen className="size-6 text-purple" />
        <span className="ops-label text-acid">{label}</span>
      </div>
      <div>
        <h3 className="text-xl font-semibold">{topic.topicName}</h3>
        <p className="mt-2 text-xs text-muted-foreground">
          {topic.questionCount} questions ·{" "}
          {Object.entries(topic.difficultyDistribution)
            .map(([level, n]) => `${n} ${level}`)
            .join(" / ")}
        </p>
      </div>
      <div className="mt-auto grid grid-cols-2 gap-3">
        <label className="space-y-2">
          <span className="ops-label">Questions</span>
          <Input
            aria-label={`${topic.topicName} question count`}
            type="number"
            min={1}
            max={Math.min(topic.questionCount, 200)}
            step={1}
            value={Number.isNaN(count) ? "" : count}
            onChange={(e) => setCount(e.target.valueAsNumber)}
          />
        </label>
        <label className="space-y-2">
          <span className="ops-label">Time limit</span>
          <select
            aria-label={`${topic.topicName} time limit`}
            value={seconds}
            onChange={(e) => setSeconds(Number(e.target.value))}
            className="h-9 w-full rounded-lg border border-input bg-background px-2 text-sm"
          >
            <option value={60}>1 minute</option>
            <option value={180}>3 minutes</option>
            <option value={300}>5 minutes</option>
            <option value={600}>10 minutes</option>
            <option value={900}>15 minutes</option>
          </select>
        </label>
      </div>
      <p className="text-xs text-muted-foreground">
        Answers lock on submission. The timer starts when you begin.
      </p>
      {error && (
        <p role="alert" className="text-sm text-coral">
          {error}
        </p>
      )}
      <Button
        className="min-h-10 w-full"
        disabled={busy || !sprintSettings(count, seconds, topic.questionCount)}
        onClick={() => void start()}
      >
        {busy ? "Starting…" : "Start sprint"}
        <ArrowRight />
      </Button>
    </BrutalCard>
  );
}

function LearningPageContent() {
  const params = useSearchParams();
  const router = useRouter();
  const jobId = params.get("jobId") || "";
  const [search, setSearch] = useState("");
  const topics = useSWR<LearningTopic[]>("/api/learning/topics");
  const history = useSWR<SprintAttempt[]>("/api/learning/attempts");
  const jobs = useSWR<JobPage>(
    `/api/jobs?pageSize=20&search=${encodeURIComponent(search)}`,
  );
  const gap = useSWR<SkillGap>(
    jobId ? `/api/jobs/${encodeURIComponent(jobId)}/skill-gap` : null,
  );
  const [active, setActive] = useState<SprintAttempt | null>(null);
  const [error, setError] = useState<string>();
  const [loadingAttempt, setLoadingAttempt] = useState(false);
  const mutateHistory = history.mutate;
  const refresh = useCallback(() => {
    void mutateHistory();
  }, [mutateHistory]);
  const recommended = gap.data?.hasResume
    ? gap.data.missing.flatMap((skill) =>
        skill.topicIds.map((id) => ({ id, level: skill.requirement })),
      )
    : [];
  const ordered = [...(topics.data ?? [])].sort((a, b) => {
    const priority = (id: string) =>
      recommended.find((x) => x.id === id)?.level === "required" ? 0 : 1;
    return priority(a.topicId) - priority(b.topicId);
  });

  async function resume(id: string) {
    setLoadingAttempt(true);
    setError(undefined);
    try {
      setActive(
        await apiRequest<SprintAttempt>(
          `/api/learning/attempts/${encodeURIComponent(id)}`,
        ),
      );
    } catch (cause) {
      setError(errorSummary(cause));
    } finally {
      setLoadingAttempt(false);
    }
  }

  return (
    <div className="space-y-8">
      <RouteHeader
        eyebrow="Interview preparation"
        path="/learning"
        title="Close the skill gap."
        description="Compare your resume with a role, then practise the skills you need through focused, timed sprints."
      />
      {active ? (
        <LearningSprint
          key={active.id}
          initialAttempt={active}
          onUpdate={refresh}
          onClose={() => {
            setActive(null);
            refresh();
          }}
        />
      ) : (
        <>
          <BrutalCard className="space-y-5">
            <div className="flex items-center gap-3">
              <Target className="size-5 text-purple" />
              <h2 className="text-xl font-semibold">Choose your target role</h2>
            </div>
            <p className="text-sm text-muted-foreground">
              Required gaps come first. Preferred skills and uncertain
              requirements stay labeled for review.
            </p>
            <label className="block max-w-lg space-y-2">
              <span className="ops-label">Find a job</span>
              <Input
                placeholder="Search company or title"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <label className="block max-w-lg space-y-2">
              <span className="ops-label">Target job</span>
              <select
                className="min-h-11 w-full rounded-lg border border-input bg-background px-3 text-sm"
                value={jobId}
                onChange={(e) =>
                  router.replace(
                    e.target.value
                      ? `/learning?jobId=${encodeURIComponent(e.target.value)}`
                      : "/learning",
                  )
                }
              >
                <option value="">Browse practice topics</option>
                {jobId &&
                  !jobs.data?.items.some((item) => item.id === jobId) && (
                    <option value={jobId}>
                      {gap.data?.jobTitle ?? "Selected job"}
                    </option>
                  )}
                {jobs.data?.items.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.roleTitle} · {job.companyName}
                  </option>
                ))}
              </select>
            </label>
            {jobs.error && (
              <p role="alert" className="text-sm text-coral">
                {errorSummary(jobs.error)}
              </p>
            )}
            {!jobs.isLoading &&
              !jobs.error &&
              jobs.data?.items.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No jobs found. Import jobs or change your search.
                </p>
              )}
            {jobId && gap.isLoading && <Skeleton className="h-24" />}
            {gap.error && (
              <p role="alert" className="text-sm text-coral">
                {errorSummary(gap.error)}
              </p>
            )}
            {gap.data && <SkillGapDetails gap={gap.data} />}
            {!jobId && (
              <p className="text-sm text-muted-foreground">
                Choose a role to build a learning path. You can also practise
                available topics below.
              </p>
            )}
          </BrutalCard>
          <section className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 className="text-2xl font-semibold">
                {jobId ? "Your learning path" : "Practice library"}
              </h2>
              <span className="ops-label text-muted-foreground">
                Theoretical practice / explanations included
              </span>
            </div>
            {topics.isLoading && <Skeleton className="h-64" />}
            {topics.error && (
              <p role="alert" className="text-sm text-coral">
                {errorSummary(topics.error)}{" "}
                <Button variant="outline" onClick={() => void topics.mutate()}>
                  Retry
                </Button>
              </p>
            )}
            {jobId && gap.data && !recommended.length && (
              <p className="rounded-lg border border-border p-5 text-sm leading-6 text-muted-foreground">
                {!gap.data.hasResume
                  ? "Upload a resume to unlock recommendations for this role."
                  : gap.data.missing.length
                    ? "No question banks are available for these gaps yet."
                    : "No additional practice is recommended for the recognized skills in this role."}
              </p>
            )}
            <div className="grid gap-5 lg:grid-cols-2">
              {ordered
                .filter(
                  (topic) =>
                    !jobId || recommended.some((x) => x.id === topic.topicId),
                )
                .map((topic) => (
                  <TopicCard
                    key={`${jobId}-${topic.topicId}`}
                    topic={topic}
                    jobId={jobId || undefined}
                    label={
                      jobId
                        ? recommended.find((x) => x.id === topic.topicId)
                            ?.level === "required"
                          ? "Required gap"
                          : "Optional practice"
                        : "Available track"
                    }
                    onStart={(attempt) => {
                      setActive(attempt);
                      refresh();
                    }}
                  />
                ))}
            </div>
            {jobId && (
              <Link
                className="inline-flex min-h-10 items-center gap-2 text-sm text-purple"
                href="/learning"
              >
                Browse the practice library
                <ArrowRight className="size-4" />
              </Link>
            )}
            {topics.data?.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No question banks are available yet.
              </p>
            )}
          </section>
          <section className="space-y-4">
            <div className="flex items-center gap-3">
              <Clock3 className="size-5 text-purple" />
              <h2 className="text-2xl font-semibold">Your recent sprints</h2>
            </div>
            {error && (
              <p role="alert" className="text-sm text-coral">
                {error}
              </p>
            )}
            {history.error && (
              <p role="alert" className="text-sm text-coral">
                {errorSummary(history.error)}
              </p>
            )}
            {history.isLoading && <Skeleton className="h-24" />}
            {history.data?.length === 0 && (
              <p className="rounded-lg border border-border p-5 text-sm text-muted-foreground">
                Your practice history will appear here. Start a sprint to begin.
              </p>
            )}
            <div className="space-y-3">
              {history.data?.map((attempt) => (
                <BrutalCard
                  key={attempt.id}
                  className="flex flex-wrap items-center justify-between gap-4"
                >
                  <div>
                    <h3 className="font-semibold">{attempt.topicName}</h3>
                    <p className="mt-2 text-xs text-muted-foreground">
                      {new Date(attempt.startedAt).toLocaleString()} ·{" "}
                      {attempt.status.toLowerCase()} · {attempt.correct}/
                      {attempt.questions.length} correct
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    disabled={loadingAttempt}
                    onClick={() => void resume(attempt.id)}
                  >
                    {attempt.status === "ACTIVE"
                      ? "Resume sprint"
                      : "Review results"}
                    <ArrowRight />
                  </Button>
                </BrutalCard>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

export default function LearningPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <LearningPageContent />
    </Suspense>
  );
}
