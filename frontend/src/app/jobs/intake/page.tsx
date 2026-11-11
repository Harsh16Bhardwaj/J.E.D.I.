"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { BrutalCard } from "@/components/brutal-card";
import { DraftSkillFit } from "@/components/draft-skill-fit";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileText,
  Link2,
  LoaderCircle,
  RotateCcw,
  SearchCheck,
  ShieldCheck,
  X,
  TriangleAlert,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, errorSummary, type User } from "@/lib/api";

const endpoint = "/api/job-drafts";
const textFields = [
  ["title", "Job title"],
  ["employer", "Employer"],
  ["location", "Location"],
  ["employmentType", "Employment type"],
  ["education", "Education and credentials"],
  ["authorization", "Work authorization or sponsorship"],
  ["compensation", "Compensation"],
] as const;
const listFields = [
  ["requiredSkills", "Required skills"],
  ["preferredSkills", "Preferred skills"],
  ["mentionedSkills", "Mentioned or unclear skills"],
  ["responsibilities", "Responsibilities"],
] as const;

type TextKey = (typeof textFields)[number][0];
type ListKey = (typeof listFields)[number][0];
type WorkMode = "REMOTE" | "HYBRID" | "ON_SITE";
type Fields = Record<TextKey, string> &
  Record<ListKey, string[]> & {
    workMode: WorkMode | null;
    experienceMinYears: number | null;
    experienceMaxYears: number | null;
  };
type Editor = Record<TextKey | ListKey, string> & {
  workMode: WorkMode | "";
  experienceMinYears: string;
  experienceMaxYears: string;
};
type Preview = {
  fields: Fields;
  sourceUrl?: string | null;
  evidence: { field: string; text: string; inferred?: boolean }[];
  warnings: string[];
  requirements?: {
    level: "required" | "preferred" | "uncertain";
    match: "all" | "any" | "review";
    skills: string[];
    experienceMinYears: number | null;
    experienceMaxYears: number | null;
    text: string;
  }[];
};
type DraftSummary = {
  id: string;
  title: string;
  employer: string;
  updatedAt: string;
};
type Draft = Preview & {
  id: string;
  description: string;
  revision: number;
  updatedAt: string;
  trackedApplication: boolean;
};
type LinkedPreview = Preview & { description: string; sourceUrl: string };

function editFields(fields: Fields): Editor {
  return {
    ...fields,
    workMode: fields.workMode ?? "",
    experienceMinYears: fields.experienceMinYears?.toString() ?? "",
    experienceMaxYears: fields.experienceMaxYears?.toString() ?? "",
    requiredSkills: fields.requiredSkills.join("\n"),
    preferredSkills: fields.preferredSkills.join("\n"),
    mentionedSkills: fields.mentionedSkills.join("\n"),
    responsibilities: fields.responsibilities.join("\n"),
  };
}

function lines(value: string) {
  return [
    ...new Set(
      value
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
    ),
  ];
}

function saveFields(editor: Editor): Fields {
  return {
    ...editor,
    workMode: editor.workMode || null,
    experienceMinYears:
      editor.experienceMinYears === ""
        ? null
        : Number(editor.experienceMinYears),
    experienceMaxYears:
      editor.experienceMaxYears === ""
        ? null
        : Number(editor.experienceMaxYears),
    requiredSkills: lines(editor.requiredSkills),
    preferredSkills: lines(editor.preferredSkills),
    mentionedSkills: lines(editor.mentionedSkills),
    responsibilities: lines(editor.responsibilities),
  };
}

function draftRequest<T>(path = "", init: RequestInit = {}) {
  return apiRequest<T>(endpoint + path, {
    signal: AbortSignal.timeout(15_000),
    ...init,
  });
}

const inputClass = "mt-1 min-h-10 w-full";

function JobIntakeWorkspace({ linkedDraft }: { linkedDraft: string | null }) {
  // Private draft bodies stay in component memory rather than the app's
  // sessionStorage-backed SWR cache.
  const [mode, setMode] = useState<"link" | "paste">(
    linkedDraft ? "paste" : "link",
  );
  const [elapsed, setElapsed] = useState(0);
  const activeRequest = useRef<AbortController | null>(null);
  useEffect(() => () => activeRequest.current?.abort(), []);
  const [drafts, setDrafts] = useState<DraftSummary[]>();
  const [listError, setListError] = useState<string>();
  const [description, setDescription] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [reviewed, setReviewed] = useState<{
    description: string;
    preview: Preview;
  }>();
  const [editor, setEditor] = useState<Editor>();
  const [identity, setIdentity] = useState<{ id: string; revision: number }>();
  const [busy, setBusy] = useState<
    "preview" | "url" | "save" | "open" | "delete" | "track" | undefined
  >(linkedDraft ? "open" : undefined);
  const [message, setMessage] = useState<{
    text: string;
    error?: boolean;
    retry?: "url" | "preview";
  }>();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [tracked, setTracked] = useState(false);

  useEffect(() => {
    if (busy !== "url" && busy !== "preview") return;
    const start = Date.now();
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - start) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [busy]);

  const showDraft = useCallback((draft: Draft) => {
    setIdentity({ id: draft.id, revision: draft.revision });
    setDescription(draft.description);
    setJobUrl(draft.sourceUrl ?? "");
    setReviewed({ description: draft.description, preview: draft });
    setEditor(editFields(draft.fields));
    setTracked(draft.trackedApplication);
    setDirty(false);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const signal = AbortSignal.any([
      controller.signal,
      AbortSignal.timeout(15_000),
    ]);
    void draftRequest<DraftSummary[]>("", { signal }).then(
      setDrafts,
      (error) => {
        if (!controller.signal.aborted) setListError(errorSummary(error));
      },
    );
    if (linkedDraft) {
      void draftRequest<Draft>(`/${linkedDraft}`, { signal })
        .then((draft) => {
          if (!controller.signal.aborted) showDraft(draft);
        })
        .catch((error) => {
          if (!controller.signal.aborted)
            setMessage({ text: errorSummary(error), error: true });
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(undefined);
        });
    }
    return () => controller.abort();
  }, [linkedDraft, showDraft]);

  async function reloadDrafts() {
    setListError(undefined);
    try {
      setDrafts(await draftRequest<DraftSummary[]>());
    } catch (error) {
      setListError(errorSummary(error));
    }
  }

  async function openDraft(id: string) {
    if (
      busy ||
      (dirty && !window.confirm("Discard unsaved changes and open this draft?"))
    )
      return;
    setBusy("open");
    setConfirmDelete(false);
    setMessage(undefined);
    try {
      showDraft(await draftRequest<Draft>(`/${id}`));
    } catch (error) {
      setMessage({ text: errorSummary(error), error: true });
    } finally {
      setBusy(undefined);
    }
  }

  function startNew() {
    if (
      dirty &&
      !window.confirm("Discard unsaved changes and start a new draft?")
    )
      return;
    setIdentity(undefined);
    setTracked(false);
    setDescription("");
    setJobUrl("");
    setReviewed(undefined);
    setEditor(undefined);
    setDirty(false);
    setConfirmDelete(false);
    setMessage(undefined);
  }

  async function trackDraft() {
    if (busy || !identity || dirty || tracked) return;
    setBusy("track");
    setMessage(undefined);
    try {
      await draftRequest(`/${identity.id}/application`, { method: "POST" });
      setTracked(true);
      setMessage({ text: "Added to your private applications." });
    } catch (error) {
      setMessage({ text: errorSummary(error), error: true });
    } finally {
      setBusy(undefined);
    }
  }

  async function extract() {
    if (busy || description.trim().length < 20) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setElapsed(0);
    setBusy("preview");
    setMessage(undefined);
    try {
      const text = description.trim();
      const preview = await draftRequest<Preview>("/preview", {
        method: "POST",
        signal: AbortSignal.any([
          controller.signal,
          AbortSignal.timeout(15_000),
        ]),
        body: JSON.stringify({ description: text }),
      });
      setReviewed({
        description: text,
        preview: {
          ...preview,
          sourceUrl:
            reviewed?.description === text ? reviewed.preview.sourceUrl : null,
        },
      });
      setEditor(editFields(preview.fields));
      setDirty(true);
    } catch (error) {
      setMessage(
        controller.signal.aborted
          ? { text: "Analysis stopped. Your input is still here." }
          : { text: errorSummary(error), error: true, retry: "preview" },
      );
    } finally {
      activeRequest.current = null;
      setBusy(undefined);
    }
  }

  async function extractUrl() {
    if (busy || !jobUrl.trim()) return;
    if (
      dirty &&
      description.trim() &&
      !window.confirm("Replace the current text and preview with this posting?")
    )
      return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setElapsed(0);
    setBusy("url");
    setMessage(undefined);
    try {
      const preview = await draftRequest<LinkedPreview>("/preview-url", {
        method: "POST",
        signal: AbortSignal.any([
          controller.signal,
          AbortSignal.timeout(15_000),
        ]),
        body: JSON.stringify({ url: jobUrl.trim() }),
      });
      setJobUrl(preview.sourceUrl);
      setDescription(preview.description);
      setReviewed({ description: preview.description, preview });
      setEditor(editFields(preview.fields));
      setDirty(true);
    } catch (error) {
      setMessage(
        controller.signal.aborted
          ? { text: "Analysis stopped. Your input is still here." }
          : { text: errorSummary(error), error: true, retry: "url" },
      );
    } finally {
      activeRequest.current = null;
      setBusy(undefined);
    }
  }

  useEffect(() => {
    if (!reviewed) return;
    document.getElementById("job-review")?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
      block: "start",
    });
  }, [reviewed]);

  const previewCurrent = reviewed?.description === description.trim();

  async function save() {
    if (busy || !editor || !previewCurrent) return;
    const fields = saveFields(editor);
    if (
      fields.experienceMinYears !== null &&
      fields.experienceMaxYears !== null &&
      fields.experienceMinYears > fields.experienceMaxYears
    ) {
      setMessage({
        text: "Maximum experience must be at least the minimum.",
        error: true,
      });
      return;
    }
    for (const [key, label] of listFields) {
      const limit = key === "responsibilities" ? 40 : 100;
      const length = key === "responsibilities" ? 1_000 : 100;
      if (
        fields[key].length > limit ||
        fields[key].some((line) => line.length > length)
      ) {
        setMessage({
          text: `${label} can contain up to ${limit} lines of ${length} characters each.`,
          error: true,
        });
        return;
      }
    }
    const draft = identity ?? { id: crypto.randomUUID(), revision: 0 };
    setIdentity(draft);
    setBusy("save");
    setMessage(undefined);
    try {
      const saved = await draftRequest<Draft>(`/${draft.id}`, {
        method: "PUT",
        body: JSON.stringify({
          description: reviewed.description,
          fields,
          revision: draft.revision,
          sourceUrl: reviewed.preview.sourceUrl ?? null,
        }),
      });
      showDraft(saved);
      setDrafts((current) => [
        {
          id: saved.id,
          title: saved.fields.title,
          employer: saved.fields.employer,
          updatedAt: saved.updatedAt,
        },
        ...(current ?? []).filter((item) => item.id !== saved.id),
      ]);
      setMessage({ text: "Private draft saved." });
    } catch (error) {
      setMessage({ text: errorSummary(error), error: true });
    } finally {
      setBusy(undefined);
    }
  }

  async function remove() {
    if (busy || !identity || !confirmDelete) return;
    setBusy("delete");
    try {
      await draftRequest<void>(
        `/${identity.id}?revision=${identity.revision}`,
        { method: "DELETE" },
      );
      setDrafts((current) =>
        current?.filter((item) => item.id !== identity.id),
      );
      setIdentity(undefined);
      setTracked(false);
      setDescription("");
      setJobUrl("");
      setReviewed(undefined);
      setEditor(undefined);
      setConfirmDelete(false);
      setDirty(false);
      setMessage({ text: "Draft deleted." });
    } catch (error) {
      setMessage({ text: errorSummary(error), error: true });
    } finally {
      setBusy(undefined);
    }
  }

  function change<K extends keyof Editor>(key: K, value: Editor[K]) {
    setEditor((current) => current && { ...current, [key]: value });
    setDirty(true);
  }

  return (
    <div className="space-y-6">
      <header className="intake-titlebar">
        <Link href="/jobs" className="desk-back-link">
          <ArrowLeft className="size-3.5" /> Jobs
        </Link>
        <p className="desk-eyebrow">Your private workspace</p>
        <h1>
          Found something <em>interesting?</em>
        </h1>
        <p>Bring the listing. We’ll help you read between the lines.</p>
      </header>
      <ol className="intake-steps" aria-label="Job intake progress">
        {["Bring a job", "Review the details", "Compare your fit"].map(
          (step, index) => (
            <li
              key={step}
              aria-current={
                index === (identity && !dirty ? 2 : reviewed ? 1 : 0)
                  ? "step"
                  : undefined
              }
            >
              <span>{index + 1}</span>
              {step}
            </li>
          ),
        )}
      </ol>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="min-w-0 space-y-4">
          <section
            className="intake-workbench"
            aria-label="Add a job"
            aria-busy={busy === "url" || busy === "preview"}
          >
            <div
              className="intake-mode-switch"
              role="group"
              aria-label="Input method"
            >
              <button
                aria-pressed={mode === "link"}
                disabled={Boolean(busy)}
                onClick={() => setMode("link")}
              >
                <Link2 className="size-4" /> Use a link
              </button>
              <button
                aria-pressed={mode === "paste"}
                disabled={Boolean(busy)}
                onClick={() => setMode("paste")}
              >
                <FileText className="size-4" /> Paste the description
              </button>
            </div>
            <div className="intake-input-panel">
              {mode === "link" ? (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void extractUrl();
                  }}
                >
                  <div className="intake-input-icon">
                    <Link2 className="size-7" strokeWidth={1.4} />
                  </div>
                  <h2>One link. A clearer picture.</h2>
                  <p id="job-link-help">
                    Greenhouse, Lever, Ashby, and SmartRecruiters posting links
                    work here.
                  </p>
                  <label htmlFor="job-link" className="sr-only">
                    Job link
                  </label>
                  <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                    <Input
                      id="job-link"
                      type="url"
                      inputMode="url"
                      aria-describedby="job-link-help"
                      placeholder="Paste the job posting link…"
                      className="min-h-12 min-w-0 flex-1 bg-card"
                      value={jobUrl}
                      maxLength={2000}
                      disabled={Boolean(busy)}
                      onChange={(event) => setJobUrl(event.target.value)}
                    />
                    <Button
                      className="min-h-12 px-5"
                      type="submit"
                      disabled={Boolean(busy) || !jobUrl.trim()}
                    >
                      {busy === "url" ? (
                        <>
                          <LoaderCircle className="size-4 animate-spin" />{" "}
                          Reading…
                        </>
                      ) : (
                        <>
                          Read this job <ArrowRight className="size-4" />
                        </>
                      )}
                    </Button>
                  </div>
                  <p className="intake-helper">
                    Another site?{" "}
                    <button
                      type="button"
                      disabled={Boolean(busy)}
                      onClick={() => setMode("paste")}
                    >
                      Paste the description instead ↗
                    </button>
                  </p>
                </form>
              ) : (
                <div>
                  <div className="intake-input-icon">
                    <FileText className="size-7" strokeWidth={1.4} />
                  </div>
                  <h2>The details make the difference.</h2>
                  <p id="job-paste-help">
                    Copy the title, company, and requirements from the listing.
                  </p>
                  <label htmlFor="job-paste" className="sr-only">
                    Job description
                  </label>
                  <Textarea
                    id="job-paste"
                    aria-describedby="job-paste-help"
                    placeholder="Paste the job description here…"
                    className="mt-6 min-h-52 w-full bg-card"
                    value={description}
                    maxLength={20000}
                    disabled={Boolean(busy)}
                    onChange={(event) => {
                      setDescription(event.target.value);
                      setDirty(true);
                    }}
                  />
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                    <span className="text-xs text-muted-foreground">
                      {description.trim().length < 20
                        ? "At least 20 characters"
                        : `${description.length.toLocaleString()} / 20,000 characters`}
                    </span>
                    <Button
                      className="min-h-11"
                      disabled={Boolean(busy) || description.trim().length < 20}
                      onClick={() => void extract()}
                    >
                      {busy === "preview" ? (
                        <>
                          <LoaderCircle className="size-4 animate-spin" />{" "}
                          Reading…
                        </>
                      ) : (
                        <>
                          {reviewed ? "Read again" : "Find the key details"}{" "}
                          <SearchCheck className="size-4" />
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </div>
            <p className="intake-privacy">
              <ShieldCheck className="size-3.5" /> Your draft and comparisons
              are private.
            </p>
          </section>
          {(busy === "url" || busy === "preview") && (
            <section
              role="status"
              aria-live="polite"
              className="intake-processing"
            >
              <div className="intake-processing-mark">
                <LoaderCircle className="size-7 animate-spin" />
              </div>
              <div className="min-w-0 flex-1">
                <h2>
                  {busy === "url"
                    ? "Reading the posting…"
                    : "Pulling out the key details…"}
                </h2>
                <p>
                  {elapsed >= 8
                    ? "This is taking a little longer. We’ll stop after 15 seconds so you can retry."
                    : "Looking for the role, skills, and experience requirements."}
                </p>
                <span className="text-xs text-muted-foreground">
                  {elapsed}s elapsed
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => activeRequest.current?.abort()}
              >
                <X className="size-3.5" /> Stop
              </Button>
            </section>
          )}
          {message && (
            <section
              role={message.error ? "alert" : "status"}
              className={
                message.error ? "intake-feedback is-error" : "intake-feedback"
              }
            >
              {message.error ? (
                <TriangleAlert className="size-5 shrink-0" />
              ) : (
                <Check className="size-5 shrink-0" />
              )}
              <div>
                <h2>
                  {message.error
                    ? message.retry === "url"
                      ? "That link needs another way in."
                      : "We couldn’t complete that step."
                    : message.text}
                </h2>
                {message.error && <p>{message.text}</p>}
                {message.retry && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={Boolean(busy)}
                      onClick={() =>
                        void (message.retry === "url"
                          ? extractUrl()
                          : extract())
                      }
                    >
                      <RotateCcw className="size-3.5" /> Try again
                    </Button>
                    {message.retry === "url" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={Boolean(busy)}
                        onClick={() => {
                          setMode("paste");
                          setMessage(undefined);
                        }}
                      >
                        Paste description instead{" "}
                        <ArrowRight className="size-3.5" />
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </section>
          )}
          {busy === "open" && (
            <p role="status" className="text-sm text-muted-foreground">
              Opening draft…
            </p>
          )}
          {reviewed && editor && (
            <BrutalCard id="job-review" className="scroll-mt-6 space-y-4">
              <div className="intake-review-heading">
                <span>
                  <Check className="size-5" />
                </span>
                <div>
                  <p className="desk-eyebrow">Ready for your review</p>
                  <h2>{editor.title || "Your job brief"}</h2>
                  <p>
                    {editor.employer || "Check the employer below"}
                    {editor.location ? ` · ${editor.location}` : ""}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {reviewed.preview.fields.requiredSkills
                  .slice(0, 8)
                  .map((skill) => (
                    <span
                      key={skill}
                      className="rounded-full bg-acid/10 px-3 py-1 text-xs text-acid"
                    >
                      {skill}
                    </span>
                  ))}
              </div>
              {reviewed.preview.sourceUrl && (
                <a
                  href={reviewed.preview.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block text-sm text-purple underline"
                >
                  Open original posting
                </a>
              )}
              <p className="text-sm text-muted-foreground">
                Blank fields need your review. Check requirements and years of
                experience against the original posting.
              </p>
              {!previewCurrent && (
                <p role="status" className="text-sm text-coral">
                  The description changed. Extract it again before saving.
                </p>
              )}
              {reviewed.preview.warnings.length > 0 && (
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {reviewed.preview.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              )}
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void save();
                }}
              >
                <details className="intake-edit-details">
                  <summary>Edit extracted details</summary>
                  <fieldset
                    disabled={Boolean(busy)}
                    className="grid gap-4 sm:grid-cols-2"
                  >
                    {textFields.map(([key, label]) => (
                      <div key={key} className="min-w-0">
                        <label htmlFor={key} className="text-sm">
                          {label}
                        </label>
                        <Input
                          id={key}
                          className={inputClass}
                          maxLength={300}
                          value={editor[key]}
                          onChange={(event) => change(key, event.target.value)}
                        />
                      </div>
                    ))}
                    <div>
                      <label htmlFor="workMode" className="text-sm">
                        Work mode
                      </label>
                      <select
                        id="workMode"
                        className={`${inputClass} rounded-lg border border-border bg-background px-2`}
                        value={editor.workMode}
                        onChange={(event) =>
                          change(
                            "workMode",
                            event.target.value as Editor["workMode"],
                          )
                        }
                      >
                        <option value="">Unknown</option>
                        <option value="REMOTE">Remote</option>
                        <option value="HYBRID">Hybrid</option>
                        <option value="ON_SITE">On-site</option>
                      </select>
                    </div>
                    {(
                      ["experienceMinYears", "experienceMaxYears"] as const
                    ).map((key) => (
                      <div key={key}>
                        <label htmlFor={key} className="text-sm">
                          {key === "experienceMinYears"
                            ? "Minimum experience (years)"
                            : "Maximum experience (years)"}
                        </label>
                        <Input
                          id={key}
                          className={inputClass}
                          type="number"
                          min={0}
                          max={80}
                          step="any"
                          value={editor[key]}
                          onChange={(event) => change(key, event.target.value)}
                        />
                      </div>
                    ))}
                    {listFields.map(([key, label]) => (
                      <div key={key} className="min-w-0">
                        <label htmlFor={key} className="text-sm">
                          {label}
                        </label>
                        <Textarea
                          id={key}
                          className="mt-1 min-h-24 w-full"
                          placeholder="One item per line"
                          value={editor[key]}
                          onChange={(event) => change(key, event.target.value)}
                        />
                      </div>
                    ))}
                  </fieldset>
                </details>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button
                    type="submit"
                    disabled={Boolean(busy) || !previewCurrent}
                  >
                    {busy === "save" ? "Saving…" : "Save private draft"}
                  </Button>
                  {identity && identity.revision > 0 && !confirmDelete && (
                    <Button
                      type="button"
                      variant="outline"
                      disabled={Boolean(busy)}
                      onClick={() => setConfirmDelete(true)}
                    >
                      Delete draft
                    </Button>
                  )}
                  {confirmDelete && (
                    <>
                      <Button
                        type="button"
                        variant="destructive"
                        disabled={Boolean(busy)}
                        onClick={() => void remove()}
                      >
                        {busy === "delete" ? "Deleting…" : "Confirm delete"}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        disabled={Boolean(busy)}
                        onClick={() => setConfirmDelete(false)}
                      >
                        Keep draft
                      </Button>
                    </>
                  )}
                </div>
              </form>
              {confirmDelete && tracked && (
                <p role="status" className="text-sm text-coral">
                  Deleting this draft also deletes its application history.
                </p>
              )}
              {Boolean(reviewed.preview.requirements?.length) && (
                <details className="rounded-lg border border-border p-3">
                  <summary className="cursor-pointer text-sm font-bold">
                    Requirements in the original text
                  </summary>
                  <ul className="mt-2 max-h-72 space-y-3 overflow-auto text-sm">
                    {reviewed.preview.requirements?.map(
                      (requirement, index) => (
                        <li key={index}>
                          <p className="font-bold">
                            {requirement.match === "review"
                              ? "Review how these skills are combined"
                              : requirement.match === "any"
                                ? requirement.skills.join(" or ")
                                : requirement.skills.join(", ") || "Experience"}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {requirement.level === "uncertain"
                              ? "Requirement level unclear"
                              : requirement.level}
                            {requirement.experienceMinYears !== null &&
                              ` · ${requirement.experienceMinYears}${requirement.experienceMaxYears === null ? "+" : `–${requirement.experienceMaxYears}`} years`}
                          </p>
                          <p className="break-words text-muted-foreground">
                            {requirement.text}
                          </p>
                        </li>
                      ),
                    )}
                  </ul>
                </details>
              )}
              {reviewed.preview.evidence.length > 0 && (
                <details className="rounded-lg border border-border p-3">
                  <summary className="cursor-pointer text-sm font-bold">
                    Evidence from the pasted text
                  </summary>
                  <ul className="mt-2 max-h-56 space-y-2 overflow-auto text-sm">
                    {reviewed.preview.evidence.map(
                      ({ field, text, inferred }, index) => (
                        <li key={index}>
                          <strong>
                            {field.replaceAll("_", " ")}
                            {inferred && " (suggested)"}
                          </strong>{" "}
                          · {text}
                        </li>
                      ),
                    )}
                  </ul>
                </details>
              )}
              {identity && identity.revision > 0 && !dirty && (
                <>
                  {tracked ? (
                    <Link
                      href="/applications#private-drafts"
                      className={buttonVariants({ variant: "outline" })}
                    >
                      View in Applications
                    </Link>
                  ) : (
                    <Button
                      type="button"
                      variant="outline"
                      disabled={Boolean(busy)}
                      onClick={() => void trackDraft()}
                    >
                      {busy === "track" ? "Adding…" : "Add to Applications"}
                    </Button>
                  )}
                  <DraftSkillFit
                    key={`${identity.id}:${identity.revision}`}
                    draftId={identity.id}
                    revision={identity.revision}
                  />
                </>
              )}
            </BrutalCard>
          )}
        </div>
        <BrutalCard>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-bold">Your job briefs</h2>
            <Button
              size="sm"
              variant="outline"
              disabled={Boolean(busy)}
              onClick={startNew}
            >
              New draft
            </Button>
          </div>
          {listError && (
            <div className="mt-2 text-sm">
              <p role="alert" className="text-coral">
                {listError}
              </p>
              <Button
                className="mt-2"
                size="sm"
                variant="outline"
                onClick={() => void reloadDrafts()}
              >
                Retry list
              </Button>
            </div>
          )}
          {!drafts && !listError && (
            <p role="status" className="mt-2 text-sm text-muted-foreground">
              Loading drafts…
            </p>
          )}
          {drafts?.length === 0 && (
            <p className="mt-2 text-sm text-muted-foreground">
              Your saved drafts will appear here.
            </p>
          )}
          {drafts && drafts.length > 0 && (
            <ul className="mt-3 max-h-96 space-y-2 overflow-auto">
              {drafts.map((draft) => (
                <li key={draft.id}>
                  <button
                    type="button"
                    disabled={Boolean(busy)}
                    aria-current={
                      identity?.id === draft.id ? "true" : undefined
                    }
                    className="w-full rounded-lg border border-border p-3 text-left hover:bg-raised aria-current:border-purple"
                    onClick={() => void openDraft(draft.id)}
                  >
                    <span className="block truncate text-sm font-bold">
                      {draft.title || "Untitled job"}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {draft.employer || "Employer unknown"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </BrutalCard>
      </div>
    </div>
  );
}

function JobIntakeSession() {
  const { data: user } = useSWR<User>("/api/auth/session");
  const draft = useSearchParams().get("draft");
  const linkedDraft =
    draft && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(draft)
      ? draft
      : null;
  return user ? (
    <JobIntakeWorkspace
      key={`${user.id}:${linkedDraft ?? ""}`}
      linkedDraft={linkedDraft}
    />
  ) : null;
}

export default function JobIntakePage() {
  return (
    <Suspense fallback={<p role="status">Loading job intake…</p>}>
      <JobIntakeSession />
    </Suspense>
  );
}
