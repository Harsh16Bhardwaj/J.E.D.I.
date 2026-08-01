"use client";

import { useState } from "react";
import { Check, Copy, KeyRound, RefreshCw, Shield, UserRound, UsersRound, X } from "lucide-react";
import { toast } from "sonner";
import useSWR, { useSWRConfig } from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { RouteHeader } from "@/components/route-header";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  apiRequest,
  errorSummary,
  isApiError,
  type CreatedInvitation,
  type GroupSettings,
  type Invitation,
} from "@/lib/api";

function RequestError({ error }: { error: unknown }) {
  return (
    <div role="alert" className="rounded-lg border border-coral/40 bg-coral/5 p-4 text-sm text-coral">
      {errorSummary(error)}
      {isApiError(error) && error.requestId && <p className="mt-1 font-mono text-xs text-muted-foreground">Request {error.requestId}</p>}
    </div>
  );
}

export default function GroupSettingsPage() {
  const group = useSWR<GroupSettings>("/api/group");
  const invitations = useSWR<Invitation[]>(group.data?.isGroupOwner ? "/api/invitations" : null);
  const { mutate } = useSWRConfig();
  const [created, setCreated] = useState<CreatedInvitation>();
  const [revoking, setRevoking] = useState<Invitation>();
  const [busy, setBusy] = useState(false);
  const [requestError, setRequestError] = useState<unknown>();
  const [renderedAt] = useState(() => Date.now());

  async function createInvitation() {
    if (busy) return;
    setBusy(true);
    setRequestError(undefined);
    try {
      const result = await apiRequest<CreatedInvitation>("/api/invitations", { method: "POST" });
      setCreated(result);
      await mutate("/api/invitations");
      toast.success("New invitation created.", { description: "The previous active code was revoked." });
    } catch (error) {
      setRequestError(error);
      toast.error(errorSummary(error));
    } finally {
      setBusy(false);
    }
  }

  async function copyCode() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.code);
      toast.success("Invitation code copied.");
    } catch {
      toast.error("Copy failed. Select the visible code manually.");
    }
  }

  async function revokeInvitation() {
    if (!revoking || busy) return;
    setBusy(true);
    setRequestError(undefined);
    try {
      await apiRequest<void>(`/api/invitations/${revoking.id}`, { method: "DELETE" });
      if (created?.id === revoking.id) setCreated(undefined);
      await mutate("/api/invitations");
      toast.success("Invitation revoked.");
      setRevoking(undefined);
    } catch (error) {
      setRequestError(error);
      toast.error(errorSummary(error));
    } finally {
      setBusy(false);
    }
  }

  if (group.isLoading) {
    return <div className="space-y-6"><Skeleton className="h-28 bg-raised" /><Skeleton className="h-96 bg-raised" /></div>;
  }
  if (group.error || !group.data) return <RequestError error={group.error ?? new Error("Group settings are unavailable.")} />;

  const activeInvitation = invitations.data?.find(
    (item) =>
      !item.revokedAt && new Date(item.expiresAt).getTime() > renderedAt,
  );

  return (
    <div className="space-y-9">
      <RouteHeader eyebrow="Shared workspace" title={group.data.group.name} path="/settings/group" description="One ranking profile, one model, and one daily job signal shared by the invited group." />

      <div className="grid gap-4 sm:grid-cols-3">
        <BrutalCard><UsersRound className="size-5 text-acid" /><p className="mt-6 ops-label text-muted-foreground">Members</p><p className="mt-2 text-3xl font-semibold">{group.data.memberCount} / 50</p></BrutalCard>
        <BrutalCard><UserRound className="size-5 text-purple" /><p className="mt-6 ops-label text-muted-foreground">Shared profile</p><p className="mt-2 text-lg font-semibold">{group.data.sharedProfile ? "Active" : "Not configured"}</p></BrutalCard>
        <BrutalCard><Shield className="size-5 text-muted-foreground" /><p className="mt-6 ops-label text-muted-foreground">Shared model</p><p className="mt-2 truncate text-lg font-semibold">{group.data.sharedModel?.name ?? "Not configured"}</p></BrutalCard>
      </div>

      {group.data.isGroupOwner && (
        <section className="rounded-xl border border-border bg-card p-5 sm:p-7">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div><p className="ops-label text-acid">Invitation access</p><h2 className="mt-2 text-2xl font-semibold">Reusable group code</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Creating a code revokes the previous active code. Share it directly; JEDI stores only its keyed hash.</p></div>
            <Button disabled={busy} onClick={() => void createInvitation()} className="min-h-11 bg-foreground text-background hover:bg-acid"><KeyRound className="size-4" />{busy ? "Generating..." : "Generate code"}</Button>
          </div>
          {created && (
            <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-acid/30 bg-acid/5 p-5">
              <div><p className="ops-label text-muted-foreground">Copy now</p><p className="mt-2 font-mono text-4xl font-black tracking-[0.25em] text-acid">{created.code}</p><p className="mt-2 text-xs text-muted-foreground">Expires {new Date(created.expiresAt).toLocaleString()}</p></div>
              <Button variant="outline" className="min-h-11" onClick={() => void copyCode()}><Copy className="size-4" /> Copy code</Button>
            </div>
          )}
          {Boolean(requestError) && <div className="mt-5"><RequestError error={requestError} /></div>}
          <div className="mt-6 border-t border-border pt-5">
            {invitations.isLoading ? <Skeleton className="h-16 bg-raised" /> : activeInvitation ? (
              <div className="flex flex-wrap items-center justify-between gap-4"><div><p className="flex items-center gap-2 text-sm font-semibold"><Check className="size-4 text-acid" /> Active invitation</p><p className="mt-1 text-xs text-muted-foreground">Used {activeInvitation.usageCount} times · expires {new Date(activeInvitation.expiresAt).toLocaleString()}</p></div><Button variant="outline" className="min-h-10 border-coral/30 text-coral" onClick={() => setRevoking(activeInvitation)}><X className="size-4" /> Revoke</Button></div>
            ) : <p className="text-sm text-muted-foreground">No active invitation code.</p>}
          </div>
        </section>
      )}

      <section>
        <div className="mb-4 flex items-end justify-between"><div><p className="ops-label text-muted-foreground">Group directory</p><h2 className="mt-2 text-2xl font-semibold">Members</h2></div><Button variant="ghost" className="min-h-10" onClick={() => void group.mutate()}><RefreshCw className="size-4" /> Refresh</Button></div>
        <div className="overflow-hidden rounded-xl border border-border">
          {group.data.members.map((member) => (
            <div key={member.id} className="grid gap-2 border-b border-border bg-card px-5 py-4 last:border-b-0 sm:grid-cols-[1fr_auto_auto] sm:items-center">
              <div><p className="font-medium">{member.email}</p><p className="mt-1 text-xs text-muted-foreground">Joined {new Date(member.joinedAt).toLocaleDateString()}</p></div>
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{member.onboardingComplete ? "Onboarded" : "Setup pending"}</span>
              {member.isOwner && <span className="w-fit rounded-full border border-purple/30 px-3 py-1 font-mono text-[10px] uppercase text-purple">Owner</span>}
            </div>
          ))}
        </div>
      </section>

      <Dialog open={Boolean(revoking)} onOpenChange={(open) => !open && !busy && setRevoking(undefined)}>
        <DialogContent showCloseButton={!busy} className="sm:max-w-lg">
          <DialogHeader><DialogTitle>Revoke invitation?</DialogTitle><DialogDescription>Anyone who has not registered will immediately lose access to this code. Existing members are unaffected.</DialogDescription></DialogHeader>
          {Boolean(requestError) && <RequestError error={requestError} />}
          <DialogFooter><Button variant="outline" disabled={busy} onClick={() => setRevoking(undefined)}>Cancel</Button><Button disabled={busy} className="bg-coral text-white hover:bg-coral/85" onClick={() => void revokeInvitation()}>{busy ? "Revoking..." : "Revoke code"}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
