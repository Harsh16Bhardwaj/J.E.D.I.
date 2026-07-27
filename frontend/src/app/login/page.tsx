import { LockKeyhole } from "lucide-react";

import { BrutalCard } from "@/components/brutal-card";
import { RouteHeader } from "@/components/route-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  return (
    <div className="space-y-10">
      <RouteHeader
        eyebrow="Private access"
        title="Keep the command center personal."
        path="/login"
        description="Authentication is intentionally not active yet. This screen establishes the future private-access entry point."
      />
      <BrutalCard className="max-w-xl bg-raised">
        <LockKeyhole className="size-9 text-acid" aria-hidden="true" />
        <label
          htmlFor="password"
          className="mt-8 block font-mono text-xs font-bold uppercase tracking-widest"
        >
          Password
        </label>
        <Input
          id="password"
          type="password"
          disabled
          placeholder="Authentication arrives in a later phase"
          className="mt-3 h-12 rounded-[3px] border-2 border-foreground bg-background"
        />
        <Button
          disabled
          className="mt-4 h-11 rounded-[3px] border-2 border-foreground bg-acid px-5 font-mono font-bold uppercase text-background"
        >
          Enter JEDI
        </Button>
      </BrutalCard>
    </div>
  );
}
