"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { BrutalCard } from "@/components/brutal-card";
import { DraftSkillFit } from "@/components/draft-skill-fit";
import { RouteHeader } from "@/components/route-header";
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
type Fields = Record<TextKey, string> & Record<ListKey, string[]> & {
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
type DraftSummary = { id: string; title: string; employer: string; updatedAt: string };
type Draft = Preview & { id: string; description: string; revision: number; updatedAt: string };
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
  return [...new Set(value.split("\n").map((line) => line.trim()).filter(Boolean))];
}

function saveFields(editor: Editor): Fields {
  return {
    ...editor,
    workMode: editor.workMode || null,
    experienceMinYears: editor.experienceMinYears === "" ? null : Number(editor.experienceMinYears),
    experienceMaxYears: editor.experienceMaxYears === "" ? null : Number(editor.experienceMaxYears),
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

function JobIntakeWorkspace() {
  // Private draft bodies stay in component memory rather than the app's
  // sessionStorage-backed SWR cache.
  const [drafts, setDrafts] = useState<DraftSummary[]>();
  const [listError, setListError] = useState<string>();
  const [description, setDescription] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [reviewed, setReviewed] = useState<{ description: string; preview: Preview }>();
  const [editor, setEditor] = useState<Editor>();
  const [identity, setIdentity] = useState<{ id: string; revision: number }>();
  const [busy, setBusy] = useState<"preview" | "url" | "save" | "open" | "delete">();
  const [message, setMessage] = useState<{ text: string; error?: boolean }>();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]);
    void draftRequest<DraftSummary[]>("", { signal }).then(setDrafts, (error) => {
      if (!controller.signal.aborted) setListError(errorSummary(error));
    });
    return () => controller.abort();
  }, []);

  async function reloadDrafts() {
    setListError(undefined);
    try {
      setDrafts(await draftRequest<DraftSummary[]>());
    } catch (error) {
      setListError(errorSummary(error));
    }
  }

  function showDraft(draft: Draft) {
    setIdentity({ id: draft.id, revision: draft.revision });
    setDescription(draft.description);
    setJobUrl(draft.sourceUrl ?? "");
    setReviewed({ description: draft.description, preview: draft });
    setEditor(editFields(draft.fields));
    setDirty(false);
  }

  async function openDraft(id: string) {
    if (busy || (dirty && !window.confirm("Discard unsaved changes and open this draft?"))) return;
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
    if (dirty && !window.confirm("Discard unsaved changes and start a new draft?")) return;
    setIdentity(undefined);
    setDescription("");
    setJobUrl("");
    setReviewed(undefined);
    setEditor(undefined);
    setDirty(false);
    setConfirmDelete(false);
    setMessage(undefined);
  }

  async function extract() {
    if (busy || description.trim().length < 20) return;
    setBusy("preview");
    setMessage(undefined);
    try {
      const text = description.trim();
      const preview = await draftRequest<Preview>("/preview", {
        method: "POST",
        body: JSON.stringify({ description: text }),
      });
      setReviewed({
        description: text,
        preview: { ...preview, sourceUrl: reviewed?.description === text ? reviewed.preview.sourceUrl : null },
      });
      setEditor(editFields(preview.fields));
      setDirty(true);
    } catch (error) {
      setMessage({ text: errorSummary(error), error: true });
    } finally {
      setBusy(undefined);
    }
  }

  async function extractUrl() {
    if (busy || !jobUrl.trim()) return;
    if (dirty && description.trim() && !window.confirm("Replace the current text and preview with this posting?")) return;
    setBusy("url");
    setMessage(undefined);
    try {
      const preview = await draftRequest<LinkedPreview>("/preview-url", {
        method: "POST",
        body: JSON.stringify({ url: jobUrl.trim() }),
      });
      setJobUrl(preview.sourceUrl);
      setDescription(preview.description);
      setReviewed({ description: preview.description, preview });
      setEditor(editFields(preview.fields));
      setDirty(true);
    } catch (error) {
      setMessage({ text: errorSummary(error), error: true });
    } finally {
      setBusy(undefined);
    }
  }

  const previewCurrent = reviewed?.description === description.trim();

  async function save() {
    if (busy || !editor || !previewCurrent) return;
    const fields = saveFields(editor);
    if (fields.experienceMinYears !== null && fields.experienceMaxYears !== null &&
        fields.experienceMinYears > fields.experienceMaxYears) {
      setMessage({ text: "Maximum experience must be at least the minimum.", error: true });
      return;
    }
    for (const [key, label] of listFields) {
      const limit = key === "responsibilities" ? 40 : 100;
      const length = key === "responsibilities" ? 1_000 : 100;
      if (fields[key].length > limit || fields[key].some((line) => line.length > length)) {
        setMessage({ text: `${label} can contain up to ${limit} lines of ${length} characters each.`, error: true });
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
        { id: saved.id, title: saved.fields.title, employer: saved.fields.employer, updatedAt: saved.updatedAt },
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
      await draftRequest<void>(`/${identity.id}?revision=${identity.revision}`, { method: "DELETE" });
      setDrafts((current) => current?.filter((item) => item.id !== identity.id));
      setIdentity(undefined);
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
      <RouteHeader path="/jobs/intake" eyebrow="Private job workspace" title="Bring a job" description="Bring a public job link or paste a description. Review the details and save a private draft." />
      <Link href="/jobs" className={buttonVariants({ variant: "outline" })}>Back to jobs</Link>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0 space-y-4">
          <BrutalCard>
            <form className="mb-5 border-b border-border pb-5" onSubmit={(event) => { event.preventDefault(); void extractUrl(); }}>
              <label htmlFor="job-link" className="text-lg font-bold">Job link</label>
              <p id="job-link-help" className="mt-1 text-sm text-muted-foreground">Use an individual Greenhouse, Lever, or Ashby posting. For other sites, paste the description below.</p>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <Input id="job-link" type="url" inputMode="url" aria-describedby="job-link-help" placeholder="https://…" className="min-h-10 flex-1" value={jobUrl} maxLength={2_000} disabled={Boolean(busy)} onChange={(event) => setJobUrl(event.target.value)} />
                <Button type="submit" variant="outline" disabled={Boolean(busy) || !jobUrl.trim()}>
                  {busy === "url" ? "Fetching posting…" : "Preview from link"}
                </Button>
              </div>
            </form>
            <label htmlFor="job-paste" className="text-lg font-bold">Job description</label>
            <p id="job-paste-help" className="mt-1 text-sm text-muted-foreground">Include the title, employer, and any requirements listed in the posting.</p>
            <Textarea id="job-paste" aria-describedby="job-paste-help" className="mt-3 min-h-52 w-full" value={description} maxLength={20_000} disabled={Boolean(busy)} onChange={(event) => { setDescription(event.target.value); setDirty(true); }} />
            <Button className="mt-3" disabled={Boolean(busy) || description.trim().length < 20} onClick={() => void extract()}>
              {busy === "preview" ? "Extracting…" : reviewed ? "Extract again" : "Preview extracted details"}
            </Button>
          </BrutalCard>
          {message && <p role={message.error ? "alert" : "status"} className={message.error ? "text-sm text-coral" : "text-sm text-acid"}>{message.text}</p>}
          {reviewed && editor && (
            <BrutalCard className="space-y-4">
              <h2 className="text-lg font-bold">Review job details</h2>
              {reviewed.preview.sourceUrl && (
                <a href={reviewed.preview.sourceUrl} target="_blank" rel="noopener noreferrer" className="inline-block text-sm text-purple underline">
                  Open original posting
                </a>
              )}
              <p className="text-sm text-muted-foreground">Blank fields need your review. Check requirements and years of experience against the original posting.</p>
              {!previewCurrent && <p role="status" className="text-sm text-coral">The description changed. Extract it again before saving.</p>}
              {reviewed.preview.warnings.length > 0 && (
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {reviewed.preview.warnings.map((warning, index) => <li key={index}>{warning}</li>)}
                </ul>
              )}
              <form onSubmit={(event) => { event.preventDefault(); void save(); }}>
                <fieldset disabled={Boolean(busy)} className="grid gap-4 sm:grid-cols-2">
                  {textFields.map(([key, label]) => (
                    <div key={key} className="min-w-0">
                      <label htmlFor={key} className="text-sm">{label}</label>
                      <Input id={key} className={inputClass} maxLength={300} value={editor[key]} onChange={(event) => change(key, event.target.value)} />
                    </div>
                  ))}
                  <div>
                    <label htmlFor="workMode" className="text-sm">Work mode</label>
                    <select id="workMode" className={`${inputClass} rounded-lg border border-border bg-background px-2`} value={editor.workMode} onChange={(event) => change("workMode", event.target.value as Editor["workMode"])}>
                      <option value="">Unknown</option>
                      <option value="REMOTE">Remote</option>
                      <option value="HYBRID">Hybrid</option>
                      <option value="ON_SITE">On-site</option>
                    </select>
                  </div>
                  {(["experienceMinYears", "experienceMaxYears"] as const).map((key) => (
                    <div key={key}>
                      <label htmlFor={key} className="text-sm">{key === "experienceMinYears" ? "Minimum experience (years)" : "Maximum experience (years)"}</label>
                      <Input id={key} className={inputClass} type="number" min={0} max={80} step="any" value={editor[key]} onChange={(event) => change(key, event.target.value)} />
                    </div>
                  ))}
                  {listFields.map(([key, label]) => (
                    <div key={key} className="min-w-0">
                      <label htmlFor={key} className="text-sm">{label}</label>
                      <Textarea id={key} className="mt-1 min-h-24 w-full" placeholder="One item per line" value={editor[key]} onChange={(event) => change(key, event.target.value)} />
                    </div>
                  ))}
                </fieldset>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button type="submit" disabled={Boolean(busy) || !previewCurrent}>{busy === "save" ? "Saving…" : "Save private draft"}</Button>
                  {identity && identity.revision > 0 && !confirmDelete && (
                    <Button type="button" variant="outline" disabled={Boolean(busy)} onClick={() => setConfirmDelete(true)}>Delete draft</Button>
                  )}
                  {confirmDelete && (
                    <>
                      <Button type="button" variant="destructive" disabled={Boolean(busy)} onClick={() => void remove()}>{busy === "delete" ? "Deleting…" : "Confirm delete"}</Button>
                      <Button type="button" variant="outline" disabled={Boolean(busy)} onClick={() => setConfirmDelete(false)}>Keep draft</Button>
                    </>
                  )}
                </div>
              </form>
              {Boolean(reviewed.preview.requirements?.length) && (
                <details className="rounded-lg border border-border p-3">
                  <summary className="cursor-pointer text-sm font-bold">Requirements in the original text</summary>
                  <ul className="mt-2 max-h-72 space-y-3 overflow-auto text-sm">
                    {reviewed.preview.requirements?.map((requirement, index) => (
                      <li key={index}>
                        <p className="font-bold">
                          {requirement.match === "review" ? "Review how these skills are combined" :
                            requirement.match === "any" ? requirement.skills.join(" or ") :
                            requirement.skills.join(", ") || "Experience"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {requirement.level === "uncertain" ? "Requirement level unclear" : requirement.level}
                          {requirement.experienceMinYears !== null &&
                            ` · ${requirement.experienceMinYears}${requirement.experienceMaxYears === null ? "+" : `–${requirement.experienceMaxYears}`} years`}
                        </p>
                        <p className="break-words text-muted-foreground">{requirement.text}</p>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {reviewed.preview.evidence.length > 0 && (
                <details className="rounded-lg border border-border p-3">
                  <summary className="cursor-pointer text-sm font-bold">Evidence from the pasted text</summary>
                  <ul className="mt-2 max-h-56 space-y-2 overflow-auto text-sm">
                    {reviewed.preview.evidence.map(({ field, text, inferred }, index) => (
                      <li key={index}><strong>{field.replaceAll("_", " ")}{inferred && " (suggested)"}</strong> · {text}</li>
                    ))}
                  </ul>
                </details>
              )}
              {identity && identity.revision > 0 && !dirty && (
                <DraftSkillFit
                  key={`${identity.id}:${identity.revision}`}
                  draftId={identity.id}
                  revision={identity.revision}
                />
              )}
            </BrutalCard>
          )}
        </div>
        <BrutalCard>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-bold">Private drafts</h2>
            <Button size="sm" variant="outline" disabled={Boolean(busy)} onClick={startNew}>New draft</Button>
          </div>
          {listError && <div className="mt-2 text-sm"><p role="alert" className="text-coral">{listError}</p><Button className="mt-2" size="sm" variant="outline" onClick={() => void reloadDrafts()}>Retry list</Button></div>}
          {!drafts && !listError && <p role="status" className="mt-2 text-sm text-muted-foreground">Loading drafts…</p>}
          {drafts?.length === 0 && <p className="mt-2 text-sm text-muted-foreground">Your saved drafts will appear here.</p>}
          {drafts && drafts.length > 0 && (
            <ul className="mt-3 max-h-96 space-y-2 overflow-auto">
              {drafts.map((draft) => (
                <li key={draft.id}>
                  <button type="button" disabled={Boolean(busy)} aria-current={identity?.id === draft.id ? "true" : undefined} className="w-full rounded-lg border border-border p-3 text-left hover:bg-raised aria-current:border-purple" onClick={() => void openDraft(draft.id)}>
                    <span className="block truncate text-sm font-bold">{draft.title || "Untitled job"}</span>
                    <span className="block truncate text-xs text-muted-foreground">{draft.employer || "Employer unknown"}</span>
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

export default function JobIntakePage() {
  const { data: user } = useSWR<User>("/api/auth/session");
  return user ? <JobIntakeWorkspace key={user.id} /> : null;
}
