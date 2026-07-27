import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { BrutalCard } from "@/components/brutal-card";
import { PageGrid } from "@/components/page-grid";
import { RouteHeader } from "@/components/route-header";
import { settingsNavigation } from "@/lib/navigation";

export default function SettingsPage() {
  return (
    <div className="space-y-10">
      <RouteHeader
        eyebrow="Configuration"
        title="Settings"
        path="/settings"
        description="Version the personal profile, approved sources, model bundles, and email-digest behavior that shape daily operations."
      />
      <PageGrid>
        {settingsNavigation
          .filter(({ href }) => href !== "/settings")
          .map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className="group">
              <BrutalCard className="flex min-h-48 flex-col justify-between transition-transform group-hover:-translate-y-1 group-hover:bg-raised">
                <div className="flex items-center justify-between">
                  <Icon className="size-7 text-purple" aria-hidden="true" />
                  <ArrowUpRight className="size-5" aria-hidden="true" />
                </div>
                <div>
                  <h2 className="text-2xl font-black uppercase">{label}</h2>
                  <code className="text-xs text-muted-foreground">{href}</code>
                </div>
              </BrutalCard>
            </Link>
          ))}
      </PageGrid>
    </div>
  );
}
