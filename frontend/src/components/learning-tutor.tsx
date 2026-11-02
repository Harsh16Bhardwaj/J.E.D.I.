"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MessageCircle, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiRequest, errorSummary } from "@/lib/api";

type Message = { role: "user" | "assistant"; content: string };

export function LearningTutor({ attemptId, questionId, autoStart = false }: {
  attemptId: string; questionId: string; autoStart?: boolean;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [open, setOpen] = useState(false);

  const requested = useRef(false);

  const ask = useCallback(async (message: string) => {
    if (busy || !message.trim()) return;
    setOpen(true);
    setBusy(true);
    setError(undefined);
    try {
      const result = await apiRequest<{ reply: string }>(
        `/api/learning/attempts/${encodeURIComponent(attemptId)}/tutor`, {
          method: "POST",
          body: JSON.stringify({ questionId, message, history: messages.slice(-6) }),
        },
      );
      setMessages((current) => [...current,
        { role: "user", content: message },
        { role: "assistant", content: result.reply },
      ]);
      setDraft("");
    } catch (cause) {
      setError(errorSummary(cause));
    } finally {
      setBusy(false);
    }
  }, [attemptId, questionId, busy, messages]);

  useEffect(() => {
    if (!autoStart || requested.current) return;
    requested.current = true;
    void ask("Explain why my answer is right or wrong, with an example.");
  }, [autoStart, ask]);

  return <section className="mt-5 border-t border-purple/20 pt-4" aria-label="AI answer tutor">
    {!open ? <Button type="button" variant="outline" onClick={() => void ask("Explain why my answer is right or wrong, with an example.")}>
      <MessageCircle className="size-4" />Ask AI about this answer
    </Button> : <>
      <h4 className="ops-label text-purple">AI tutor · Groq</h4>
      <p className="mt-2 text-xs text-muted-foreground">Only this question, your submitted answer and these messages are sent to Groq. AI explanations do not change your score.</p>
      <div className="mt-4 max-h-96 space-y-3 overflow-y-auto" role="log" aria-live="polite" aria-label="Tutor conversation">
        {messages.map((message, index) => <div key={index} className={`rounded-lg border p-3 ${message.role === "user" ? "border-border bg-background" : "border-purple/20 bg-purple/5"}`}>
          <p className="ops-label text-muted-foreground">{message.role === "user" ? "You" : "AI tutor"}</p>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{message.content}</p>
        </div>)}
      </div>
      {busy && <p role="status" className="mt-3 flex items-center gap-2 text-sm text-purple"><LoaderCircle className="size-4 animate-spin" />Thinking…</p>}
      {error && <div role="alert" className="mt-3 text-sm text-coral"><p>{error}</p><Button type="button" variant="outline" className="mt-2" disabled={busy} onClick={() => void ask(draft.trim() || "Explain why my answer is right or wrong, with an example.")}>Retry</Button></div>}
      <label className="mt-4 block text-xs text-muted-foreground">Ask a follow-up
        <Textarea className="mt-2" value={draft} maxLength={1000} disabled={busy} onChange={(event) => setDraft(event.target.value)} placeholder="Why is the other option incorrect? Show me an example." />
      </label>
      <Button type="button" className="mt-3" disabled={busy || !draft.trim()} onClick={() => void ask(draft.trim())}>Ask AI</Button>
      <p className="mt-2 text-xs text-muted-foreground">This conversation stays in this view and is not saved to your practice history.</p>
    </>}
  </section>;
}
