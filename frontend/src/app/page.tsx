import Link from "next/link";
import { ArrowUpRight, Orbit } from "lucide-react";

import { BrutalCard } from "@/components/brutal-card";
import { PageGrid } from "@/components/page-grid";
import { RouteHeader } from "@/components/route-header";
import { StatusBadge } from "@/components/status-badge";
import { allNavigation } from "@/lib/navigation";

export default function SystemIndexPage() {
  return (
    <div className="space-y-10">
      <RouteHeader
        eyebrow="System index"
        title="One place to run the job hunt."
        path="/"
        description="JEDI turns a structured daily job batch into a focused shortlist, tracks what happens next, and preserves every signal needed to improve later rankings."
      />

      <BrutalCard className="flex flex-col gap-6 bg-acid text-background sm:flex-row sm:items-end sm:justify-between">
        <div>
          <StatusBadge tone="offline">Foundation phase</StatusBadge>
          <p className="mt-5 max-w-3xl text-2xl font-black uppercase leading-tight sm:text-4xl">
            Routes, data contracts, and service boundaries are established.
          </p>
        </div>
        <Orbit className="size-16 shrink-0" strokeWidth={2.5} aria-hidden="true" />
      </BrutalCard>

      <PageGrid>
        {allNavigation
          .filter(({ href }) => href !== "/")
          .map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className="group">
              <BrutalCard className="flex h-full min-h-44 flex-col justify-between transition-transform group-hover:-translate-y-1 group-hover:bg-raised">
                <div className="flex items-center justify-between">
                  <Icon className="size-6 text-acid" aria-hidden="true" />
                  <ArrowUpRight
                    className="size-5 transition-transform group-hover:translate-x-1 group-hover:-translate-y-1"
                    aria-hidden="true"
                  />
                </div>
                <div>
                  <h2 className="text-xl font-black uppercase">{label}</h2>
                  <code className="mt-1 block font-mono text-xs text-muted-foreground">
                    {href}
                  </code>
                </div>
              </BrutalCard>
            </Link>
          ))}
      </PageGrid>
    </div>
  );
}
