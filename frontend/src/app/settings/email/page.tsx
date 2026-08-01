"use client";

import { useState } from "react";
import { Clock3, Mail, Pencil, Plus, RefreshCw, Send, Trash2, Users } from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { RouteHeader } from "@/components/route-header";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { apiRequest, errorSummary, isApiError, type EmailRecipient, type EmailRecipientWriteResult, type EmailSettings } from "@/lib/api";

function ErrorBox({ error }: { error: unknown }) {
  return (
    <div role="alert" className="rounded-lg border border-coral/35 bg-coral/5 p-3 text-sm text-coral">
      {errorSummary(error)}
      {isApiError(error) && error.requestId && (
        <details className="mt-2 text-xs text-muted-foreground">
          <summary className="cursor-pointer">Technical details</summary>
          <p className="mt-1 font-mono">Request {error.requestId}</p>
        </details>
      )}
    </div>
  );
}

function Toggle({ checked, disabled, label, onChange }: {
  checked: boolean; disabled?: boolean; label: string; onChange: (value: boolean) => void;
}) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-7 w-12 shrink-0 overflow-hidden rounded-full border ${checked ? "border-acid/50 bg-acid/30" : "border-border bg-raised"} disabled:opacity-40`}>
      <span className={`absolute left-1 top-1 size-[18px] rounded-full transition-transform ${checked ? "translate-x-5 bg-acid" : "translate-x-0 bg-muted-foreground"}`} />
    </button>
  );
}

function ConfirmDialog({ open, busy, title, description, action, onClose, onConfirm }: {
  open: boolean; busy: boolean; title: string; description: string; action: string;
  onClose: () => void; onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(value) => !value && !busy && onClose()}>
      <DialogContent showCloseButton={!busy} className="border border-coral/35 sm:max-w-lg">
        <DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{description}</DialogDescription></DialogHeader>
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
          <Button variant="destructive" disabled={busy} onClick={onConfirm}>{busy ? "Working…" : action}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function EmailSettingsPage() {
  const settings = useSWR<EmailSettings>("/api/email/settings");
  const recipients = useSWR<EmailRecipient[]>("/api/email/recipients");
  const { mutate } = useSWRConfig();
  const [draft, setDraft] = useState<Partial<Pick<EmailSettings, "enabled" | "senderName">>>({});
  const [recipientOpen, setRecipientOpen] = useState(false);
  const [editing, setEditing] = useState<EmailRecipient>();
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [deleting, setDeleting] = useState<EmailRecipient>();
  const [disableOpen, setDisableOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [manualBusy, setManualBusy] = useState(false);
  const [requestError, setRequestError] = useState<unknown>();

  const enabled = draft.enabled ?? settings.data?.enabled ?? false;
  const senderName = draft.senderName ?? settings.data?.senderName ?? "JEDI Daily Dispatch";

  const refresh = () => Promise.all([mutate("/api/email/settings"), mutate("/api/email/recipients")]);

  async function saveSettings() {
    if (busy) return;
    setBusy(true); setRequestError(undefined);
    try {
      const result = await apiRequest<EmailSettings>("/api/email/settings", {
        method: "PATCH", body: JSON.stringify({ enabled, senderName, sendAfterRanking: true }),
      });
      toast.success("Newsletter settings saved.", { description: result.enabled ? "Automatic delivery is enabled." : "Delivery is disabled." });
      setDisableOpen(false); await refresh(); setDraft({});
    } catch (error) { setRequestError(error); toast.error(errorSummary(error)); }
    finally { setBusy(false); }
  }

  async function requestManualDispatch() {
    if (manualBusy) return;
    setManualBusy(true); setRequestError(undefined);
    try {
      const result = await apiRequest<{ status: string; ready: boolean; message: string }>("/api/email/manual-dispatch", { method: "POST" });
      if (result.ready) toast.success("Manual dispatch finished.", { description: result.message });
      else toast.info("Manual dispatch is not ready yet.", { description: result.message });
    } catch (error) { setRequestError(error); toast.error(errorSummary(error)); }
    finally { setManualBusy(false); }
  }

  function openCreate() {
    setEditing(undefined); setRecipientEmail(""); setRecipientName(""); setRequestError(undefined); setRecipientOpen(true);
  }

  async function openEdit(item: EmailRecipient) {
    setBusy(true);
    try {
      const fresh = await apiRequest<EmailRecipient>(`/api/email/recipients/${item.id}`);
      setEditing(fresh); setRecipientEmail(fresh.email); setRecipientName(fresh.displayName ?? ""); setRecipientOpen(true);
    } catch (error) { toast.error(errorSummary(error)); }
    finally { setBusy(false); }
  }

  async function saveRecipient() {
    if (busy || !recipientEmail.trim()) return setRequestError(new Error("An email address is required."));
    setBusy(true); setRequestError(undefined);
    try {
      const payload = JSON.stringify({ email: recipientEmail, displayName: recipientName.trim() || null });
      if (editing) {
        await apiRequest<EmailRecipient>(`/api/email/recipients/${editing.id}`, { method: "PATCH", body: payload });
        toast.success("Recipient updated.");
      } else {
        const result = await apiRequest<EmailRecipientWriteResult>("/api/email/recipients", { method: "POST", body: payload });
        toast.success(result.replayed ? "Recipient already exists." : result.reactivated ? "Recipient reactivated." : "Recipient added.");
      }
      setRecipientOpen(false); await refresh();
    } catch (error) { setRequestError(error); toast.error(errorSummary(error)); }
    finally { setBusy(false); }
  }

  async function toggleRecipient(item: EmailRecipient, active: boolean) {
    if (busy) return;
    setBusy(true);
    try {
      await apiRequest(`/api/email/recipients/${item.id}`, { method: "PATCH", body: JSON.stringify({ active }) });
      toast.success(active ? "Recipient enabled." : "Recipient paused."); await refresh();
    } catch (error) { toast.error(errorSummary(error)); }
    finally { setBusy(false); }
  }

  async function removeRecipient() {
    if (!deleting || busy) return;
    setBusy(true);
    try {
      await apiRequest<void>(`/api/email/recipients/${deleting.id}`, { method: "DELETE" });
      toast.success("Recipient removed from future campaigns."); setDeleting(undefined); await refresh();
    } catch (error) { setRequestError(error); toast.error(errorSummary(error)); }
    finally { setBusy(false); }
  }

  if (settings.isLoading || recipients.isLoading) {
    return <div className="space-y-6"><Skeleton className="h-36 rounded-xl bg-raised" /><Skeleton className="h-72 rounded-xl bg-raised" /></div>;
  }

  const stats = [
    { icon: Users, label: "Active audience", value: `${settings.data?.activeRecipientCount ?? 0} / ${settings.data?.recipientLimit ?? 50}`, note: "Private delivery per recipient." },
    { icon: Clock3, label: "Schedule", value: "12:00 AM IST", note: "Runs daily when a ranked batch is ready." },
  ];

  return (
    <div className="space-y-9">
      <RouteHeader eyebrow="Newsletter control" title="Email dispatch" path="/settings/email"
        description="Control the daily JEDI newsletter and maintain its private recipient list. SMTP credentials never enter the browser." />
      {(settings.error || recipients.error) && <ErrorBox error={settings.error ?? recipients.error} />}

      <section className="grid gap-4 sm:grid-cols-2">
        {stats.map(({ icon: Icon, label, value, note }) => (
          <BrutalCard key={label}><Icon className="size-5 text-acid" /><p className="mt-5 ops-label text-muted-foreground">{label}</p>
            <p className="mt-2 text-xl font-semibold">{value}</p><p className="mt-2 text-sm text-muted-foreground">{note}</p></BrutalCard>
        ))}
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(18rem,.8fr)_minmax(0,1.2fr)]">
        <BrutalCard className="h-fit min-w-0">
          <div className="flex items-center gap-3"><Mail className="size-5 text-acid" /><div><p className="text-lg font-semibold">Newsletter behavior</p><p className="text-sm text-muted-foreground">Stored safely in JEDI.</p></div></div>
          <div className="mt-7 space-y-5">
            <label className="block"><span className="ops-label text-muted-foreground">Sender name</span>
              <Input className="mt-2 min-h-11" value={senderName} maxLength={100} onChange={(event) => setDraft((value) => ({ ...value, senderName: event.target.value }))} /></label>
            <div className="flex items-center justify-between gap-4 border-t pt-5"><div className="min-w-0"><p className="font-medium">Automatic daily delivery</p><p className="text-sm text-muted-foreground">Allow dispatch at 12:00 AM IST after a ranked batch is ready.</p>{!settings.data?.transportConfigured && <p className="mt-1 text-xs text-coral">SMTP must be configured on the server before this can be enabled.</p>}</div>
              <Toggle label="Automatic daily delivery" checked={enabled} disabled={!settings.data?.transportConfigured && !enabled} onChange={(value) => setDraft((current) => ({ ...current, enabled: value }))} /></div>
            <div className="rounded-xl border border-border bg-background/40 p-4">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0"><p className="font-medium">Manual dispatch</p><p className="mt-1 text-sm leading-6 text-muted-foreground">Personalize the latest ranked batch for every eligible member and send it now.</p></div>
                <Button variant="outline" className="min-h-11 shrink-0" disabled={manualBusy} onClick={() => void requestManualDispatch()}><Send />{manualBusy ? "Checking…" : "Send email now"}</Button>
              </div>
              <p className="mt-3 text-xs leading-5 text-muted-foreground">Recipients come from this list and must be linked to an onboarded group member with a profile.</p>
            </div>
            {Boolean(requestError) && !recipientOpen && !deleting && !disableOpen && <ErrorBox error={requestError} />}
            <Button className="min-h-11 w-full bg-foreground text-background hover:bg-acid" disabled={busy || !senderName.trim()}
              onClick={() => settings.data?.enabled && !enabled ? setDisableOpen(true) : void saveSettings()}>{busy ? "Saving…" : "Save configuration"}</Button>
          </div>
        </BrutalCard>

        <BrutalCard className="min-w-0">
          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"><div className="min-w-0"><p className="text-lg font-semibold">Recipients</p><p className="text-sm text-muted-foreground">Pause temporarily or remove from future campaigns.</p></div>
            <Button className="min-h-11 shrink-0 bg-foreground text-background hover:bg-acid" disabled={busy || (settings.data?.activeRecipientCount ?? 0) >= 50} onClick={openCreate}><Plus /> Add recipient</Button></div>
          <div className="mt-6 space-y-3">
            {recipients.data?.length ? recipients.data.map((item) => (
              <article key={item.id} className="grid min-w-0 gap-4 rounded-xl border bg-background/40 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <div className="min-w-0"><p className="truncate font-medium">{item.displayName || item.email}</p>{item.displayName && <p className="truncate font-mono text-xs text-muted-foreground">{item.email}</p>}</div>
                <div className="flex shrink-0 items-center gap-2 sm:justify-end"><Toggle label={`${item.active ? "Pause" : "Enable"} ${item.email}`} checked={item.active} disabled={busy} onChange={(value) => void toggleRecipient(item, value)} />
                  <Button variant="ghost" size="icon" aria-label={`Edit ${item.email}`} onClick={() => void openEdit(item)}><Pencil /></Button>
                  <Button variant="destructive" size="icon" aria-label={`Delete ${item.email}`} onClick={() => { setRequestError(undefined); setDeleting(item); }}><Trash2 /></Button></div>
              </article>
            )) : <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground"><Users className="mx-auto mb-3" />No recipients configured.</div>}
          </div>
          <Button variant="ghost" className="mt-4" disabled={busy} onClick={() => void refresh()}><RefreshCw /> Refresh</Button>
        </BrutalCard>
      </section>

      <Dialog open={recipientOpen} onOpenChange={(open) => !busy && setRecipientOpen(open)}>
        <DialogContent showCloseButton={!busy} className="border sm:max-w-lg">
          <DialogHeader><DialogTitle>{editing ? "Edit recipient" : "Add recipient"}</DialogTitle><DialogDescription>Each address receives a private message with independent delivery history.</DialogDescription></DialogHeader>
          <label><span className="ops-label text-muted-foreground">Email address</span><Input className="mt-2 min-h-11" type="email" value={recipientEmail} onChange={(event) => setRecipientEmail(event.target.value)} /></label>
          <label><span className="ops-label text-muted-foreground">Display name · optional</span><Input className="mt-2 min-h-11" value={recipientName} onChange={(event) => setRecipientName(event.target.value)} /></label>
          {Boolean(requestError) && <ErrorBox error={requestError} />}
          <DialogFooter><Button variant="outline" disabled={busy} onClick={() => setRecipientOpen(false)}>Cancel</Button><Button className="bg-foreground text-background" disabled={busy} onClick={() => void saveRecipient()}>{busy ? "Saving…" : "Save recipient"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={Boolean(deleting)} busy={busy} title="Remove this recipient?"
        description={`${deleting?.email ?? "This address"} will be excluded from future campaigns; history remains.`}
        action="Remove recipient" onClose={() => setDeleting(undefined)} onConfirm={() => void removeRecipient()} />
      <ConfirmDialog open={disableOpen} busy={busy} title="Disable newsletter delivery?"
        description="Recipients and history remain intact, but campaigns will not send until enabled again."
        action="Disable newsletter" onClose={() => setDisableOpen(false)} onConfirm={() => void saveSettings()} />
    </div>
  );
}
