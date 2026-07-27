import {
  BriefcaseBusiness,
  CheckCheck,
  Clock3,
  Sparkles,
} from "lucide-react";

import { BrutalCard } from "@/components/brutal-card";
import { DashboardStage } from "@/components/dashboard-stage";
import { PageGrid } from "@/components/page-grid";
import { RouteHeader } from "@/components/route-header";
import { StatTile } from "@/components/stat-tile";
import { StatusBadge } from "@/components/status-badge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

export default function DashboardPage() {
  return (
    <DashboardStage>
      <RouteHeader
        eyebrow="Daily overview"
        title="Your shortlist, without the noise."
        path="/dashboard"
        description="The operational home for today’s imported batch, top-25 ranking, top-10 digest, and application follow-through."
      />

      <PageGrid className="xl:grid-cols-4">
        <StatTile
          label="Jobs imported"
          value="—"
          note="Awaiting the first JSON batch."
          icon={BriefcaseBusiness}
        />
        <StatTile
          label="Top shortlist"
          value="25"
          note="Configured ranking depth."
          icon={Sparkles}
          accent="purple"
        />
        <StatTile
          label="Digest"
          value="10"
          note="Daily email target."
          icon={Clock3}
          accent="coral"
        />
        <StatTile
          label="Applied"
          value="—"
          note="No tracking data yet."
          icon={CheckCheck}
        />
      </PageGrid>

      <Tabs defaultValue="shortlist">
        <TabsList className="h-auto rounded-[4px] border-2 border-foreground bg-raised p-1">
          <TabsTrigger value="shortlist">Today&apos;s shortlist</TabsTrigger>
          <TabsTrigger value="pipeline">Application pipeline</TabsTrigger>
        </TabsList>
        <TabsContent value="shortlist" className="mt-6">
          <BrutalCard className="min-h-64 bg-raised">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-mono text-xs font-bold uppercase tracking-widest text-muted-foreground">
                  Ranking lane
                </p>
                <h2 className="mt-2 text-2xl font-black uppercase">
                  Ready for batch processing
                </h2>
              </div>
              <StatusBadge tone="queued">No batch</StatusBadge>
            </div>
            <p className="mt-14 max-w-xl text-sm leading-6 text-muted-foreground">
              Ranking data will appear here after JSON import, validation,
              deduplication, and an explicit processing action.
            </p>
          </BrutalCard>
        </TabsContent>
        <TabsContent value="pipeline" className="mt-6">
          <BrutalCard className="min-h-64 bg-raised">
            <StatusBadge tone="offline">Tracking empty</StatusBadge>
            <h2 className="mt-14 text-2xl font-black uppercase">
              Applications will move through a visible pipeline.
            </h2>
          </BrutalCard>
        </TabsContent>
      </Tabs>
    </DashboardStage>
  );
}
