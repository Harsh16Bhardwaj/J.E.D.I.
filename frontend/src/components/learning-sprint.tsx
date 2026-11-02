"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, Check, Clock3, RotateCcw } from "lucide-react";
import { LearningTutor } from "@/components/learning-tutor";
import { BrutalCard } from "@/components/brutal-card";
import { Button } from "@/components/ui/button";
import { apiRequest, errorSummary } from "@/lib/api";
import {
  nextQuestionIndex,
  remainingSeconds,
  type SprintAttempt,
  type SprintQuestion,
} from "@/lib/learning";

function Explanation({ question, attemptId, autoStart = false }: { question: SprintQuestion; attemptId: string; autoStart?: boolean }) {
  if (!question.answer) return null;
  return (
    <div
      className="mt-5 rounded-lg border border-purple/30 bg-purple/5 p-4"
      aria-live="polite"
    >
      <p className="text-sm font-semibold">
        {question.selectedOptionId === null
          ? "Unanswered"
          : question.selectedOptionId === question.answer.correctOptionId
            ? "Correct"
            : "Keep practising"}
      </p>
      <p className="mt-2 text-sm leading-6">{question.answer.explanation}</p>
      <ul className="mt-3 space-y-2 text-xs leading-5 text-muted-foreground">
        {question.options.map((option) => (
          <li key={option.id}>
            <strong
              className={
                option.id === question.answer?.correctOptionId
                  ? "text-acid"
                  : "text-foreground"
              }
            >
              {option.id.toUpperCase()}.
            </strong>{" "}
            {option.explanation}
          </li>
        ))}
      </ul>
      <LearningTutor key={question.id} attemptId={attemptId} questionId={question.id} autoStart={autoStart} />
    </div>
  );
}

export function LearningSprint({
  initialAttempt,
  onClose,
  onUpdate,
}: {
  initialAttempt: SprintAttempt;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const [attempt, setAttempt] = useState(initialAttempt);
  const [index, setIndex] = useState(() =>
    nextQuestionIndex(initialAttempt.questions),
  );
  const [autoTutorQuestionId, setAutoTutorQuestionId] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [clockOffset] = useState(
    () => Date.parse(initialAttempt.serverNow) - Date.now(),
  );
  const [remaining, setRemaining] = useState(() =>
    remainingSeconds(initialAttempt.deadlineAt, Date.now(), clockOffset),
  );
  const closing = useRef(false);
  const retryAfter = useRef(0);
  const base = `/api/learning/attempts/${encodeURIComponent(attempt.id)}`;
  const closed = attempt.status !== "ACTIVE";

  const finish = useCallback(async () => {
    if (closing.current) return;
    closing.current = true;
    setBusy(true);
    setError(undefined);
    try {
      setAttempt(
        await apiRequest<SprintAttempt>(`${base}/finish`, { method: "POST" }),
      );
      onUpdate();
    } catch (cause) {
      setError(errorSummary(cause));
      retryAfter.current = Date.now() + 10000;
    } finally {
      closing.current = false;
      setBusy(false);
    }
  }, [base, onUpdate]);

  useEffect(() => {
    if (closed) return;
    function tick() {
      const seconds = remainingSeconds(
        attempt.deadlineAt,
        Date.now(),
        clockOffset,
      );
      setRemaining(seconds);
      if (seconds === 0 && Date.now() >= retryAfter.current) void finish();
    }
    const interval = window.setInterval(tick, 500);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [attempt.deadlineAt, clockOffset, closed, finish]);

  async function submit() {
    if (!selected || busy || remaining === 0) return;
    setBusy(true);
    setError(undefined);
    try {
      setAttempt(
        await apiRequest<SprintAttempt>(`${base}/answers`, {
          method: "POST",
          body: JSON.stringify({
            questionId: attempt.questions[index].id,
            optionId: selected,
          }),
        }),
      );
      setAutoTutorQuestionId(attempt.questions[index].id);
    } catch (cause) {
      setError(errorSummary(cause));
      try {
        setAttempt(await apiRequest<SprintAttempt>(base));
      } catch {
        /* Keep the existing question available for retry. */
      }
    } finally {
      setBusy(false);
    }
  }

  const question = attempt.questions[index];
  if (closed)
    return (
      <BrutalCard className="space-y-6 p-5 sm:p-7">
        <div>
          <p className="ops-label text-acid">
            {attempt.status === "EXPIRED" ? "Time’s up" : "Sprint complete"}
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight">
            {attempt.topicName}
          </h2>
          <p className="mt-3 text-sm text-muted-foreground">
            Practice recorded. These results help you review; they do not
            certify mastery.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {[
            ["Correct", attempt.correct],
            ["Incorrect", attempt.incorrect],
            ["Unanswered", attempt.unanswered],
          ].map(([label, count]) => (
            <div key={label} className="rounded-lg border border-border p-3">
              <p className="ops-label text-muted-foreground">{label}</p>
              <p className="mt-3 text-3xl font-black">{count}</p>
            </div>
          ))}
        </div>
        <Button onClick={onClose}>
          <RotateCcw />
          Back to tracks / retry
        </Button>
        <div className="space-y-5">
          {attempt.questions.map((q, i) => (
            <section key={q.id} className="border-t border-border pt-5">
              <p className="ops-label text-muted-foreground">
                Question {i + 1} · {q.difficulty}
              </p>
              <h3 className="mt-2 font-semibold">{q.question}</h3>
              <p className="mt-2 text-xs text-muted-foreground">
                Your answer:{" "}
                {q.options.find((o) => o.id === q.selectedOptionId)?.text ??
                  "Unanswered"}
              </p>
              <Explanation question={q} attemptId={attempt.id} />
            </section>
          ))}
        </div>
      </BrutalCard>
    );

  return (
    <BrutalCard className="space-y-6 p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="ops-label text-purple">Learning sprint</p>
          <h2 className="mt-2 text-2xl font-semibold">{attempt.topicName}</h2>
        </div>
        <div
          role="timer"
          aria-label="Time remaining"
          className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 font-mono ${remaining < 30 ? "border-coral/40 text-coral" : "border-border text-acid"}`}
        >
          <Clock3 className="size-4" />
          {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}
        </div>
      </div>
      <div
        className="h-1.5 overflow-hidden rounded-full bg-raised"
        role="progressbar"
        aria-label="Questions answered"
        aria-valuemin={0}
        aria-valuemax={attempt.questions.length}
        aria-valuenow={attempt.questions.length - attempt.unanswered}
      >
        <div
          className="h-full bg-acid transition-[width] motion-reduce:transition-none"
          style={{
            width: `${(100 * (attempt.questions.length - attempt.unanswered)) / attempt.questions.length}%`,
          }}
        />
      </div>
      <fieldset
        disabled={busy || Boolean(question.selectedOptionId) || remaining === 0}
        className="space-y-3"
      >
        <legend className="mb-5">
          <span className="ops-label text-muted-foreground">
            Question {index + 1} / {attempt.questions.length} ·{" "}
            {question.difficulty}
          </span>
          <span className="mt-4 block text-xl font-semibold leading-8">
            {question.question}
          </span>
        </legend>
        {question.options.map((option) => (
          <label
            key={option.id}
            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 text-sm leading-6 ${question.selectedOptionId === option.id || selected === option.id ? "border-purple bg-purple/10" : "border-border hover:border-purple/50"}`}
          >
            <input
              className="mt-1 accent-purple"
              type="radio"
              name={`question-${question.id}`}
              value={option.id}
              checked={(question.selectedOptionId ?? selected) === option.id}
              onChange={() => setSelected(option.id)}
            />
            <span>
              <span className="mr-2 font-mono text-muted-foreground">
                {option.id.toUpperCase()}.
              </span>
              {option.text}
            </span>
            {question.answer?.correctOptionId === option.id && (
              <Check className="ml-auto mt-1 size-4 shrink-0 text-acid" />
            )}
          </label>
        ))}
      </fieldset>
      <Explanation question={question} attemptId={attempt.id} autoStart={autoTutorQuestionId === question.id} />
      {error && (
        <p role="alert" className="text-sm text-coral">
          {error}
        </p>
      )}
      {remaining === 0 && (
        <p role="status" className="text-sm text-coral">
          Time is up. Saving your results…
        </p>
      )}
      <div className="flex flex-wrap justify-between gap-3">
        <Button variant="ghost" disabled={busy} onClick={() => void finish()}>
          Finish sprint
        </Button>
        <div className="flex gap-2">
          {!question.selectedOptionId && (
            <Button
              disabled={!selected || busy || remaining === 0}
              onClick={() => void submit()}
            >
              Check answer
            </Button>
          )}
          {index < attempt.questions.length - 1 ? (
            <Button
              variant="outline"
              disabled={busy || remaining === 0}
              onClick={() => {
                setAutoTutorQuestionId(null);
                setIndex(index + 1);
                setSelected(null);
                setError(undefined);
              }}
            >
              {question.selectedOptionId ? "Next question" : "Skip for now"}
              <ArrowRight />
            </Button>
          ) : (
            <Button disabled={busy} onClick={() => void finish()}>
              See results
              <ArrowRight />
            </Button>
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Question navigation">
        {attempt.questions.map((q, i) => (
          <Button
            key={q.id}
            variant={index === i ? "default" : "outline"}
            size="sm"
            aria-label={`Question ${i + 1}${q.selectedOptionId ? ", answered" : ", unanswered"}`}
            disabled={busy || remaining === 0}
            onClick={() => {
              setAutoTutorQuestionId(null);
              setIndex(i);
              setSelected(null);
            }}
          >
            {i + 1}
            {q.selectedOptionId && <Check className="size-3" />}
          </Button>
        ))}
      </div>
    </BrutalCard>
  );
}
