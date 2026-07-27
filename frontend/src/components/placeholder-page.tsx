import { Construction } from "lucide-react";

import { BrutalCard } from "@/components/brutal-card";
import { EmptyState } from "@/components/empty-state";
import { PageGrid } from "@/components/page-grid";
import { RouteHeader } from "@/components/route-header";
import { StatusBadge } from "@/components/status-badge";

type PlaceholderPageProps = {
  eyebrow: string;
  title: string;
  path: string;
  description: string;
  nextStep: string;
};

export function PlaceholderPage({
  eyebrow,
  title,
  path,
  description,
  nextStep,
}: PlaceholderPageProps) {
  return (
    <div className="space-y-10">
      <RouteHeader
        eyebrow={eyebrow}
        title={title}
        path={path}
        description={description}
      />
      <PageGrid>
        <EmptyState
          icon={Construction}
          title="Foundation ready"
          description={nextStep}
        />
        <BrutalCard className="flex min-h-64 flex-col justify-between bg-purple text-background">
          <StatusBadge tone="offline">No live data</StatusBadge>
          <div>
            <p className="font-mono text-xs font-bold uppercase tracking-[0.16em]">
              Scope boundary
            </p>
            <p className="mt-3 text-xl font-black uppercase leading-tight">
              This screen is routed, styled, and ready for its product phase.
            </p>
          </div>
        </BrutalCard>
      </PageGrid>
    </div>
  );
}
