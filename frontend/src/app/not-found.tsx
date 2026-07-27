import Link from "next/link";
import { Radar } from "lucide-react";

import { BrutalCard } from "@/components/brutal-card";

export default function NotFound() {
  return (
    <BrutalCard className="mx-auto max-w-2xl bg-coral text-background">
      <Radar className="size-12" aria-hidden="true" />
      <p className="mt-12 font-mono text-xs font-bold uppercase tracking-widest">
        404 / route missing
      </p>
      <h1 className="mt-2 text-5xl font-black uppercase tracking-[-0.06em]">
        This signal does not exist.
      </h1>
      <Link
        href="/"
        className="mt-8 inline-block rounded-[3px] border-2 border-background bg-background px-4 py-3 font-mono text-xs font-bold uppercase tracking-widest text-foreground"
      >
        Return to system index
      </Link>
    </BrutalCard>
  );
}
