"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import useSWR from "swr";

import { BrutalCard } from "@/components/brutal-card";
import { PageGrid } from "@/components/page-grid";
import { RouteHeader } from "@/components/route-header";
import type { User } from "@/lib/api";
import { settingsNavigation, visibleNavigation } from "@/lib/navigation";

export default function SettingsPage() {
  const { data: user } = useSWR<User>("/api/auth/session");
  const items = visibleNavigation(settingsNavigation, user);

  return (
    <div className="space-y-10">
      <RouteHeader
        eyebrow="Configuration"
        title="Settings"
        path="/settings"
        description="Manage the invited group, optional delivery, and the owner-controlled systems behind the shared job workspace."
      />
      <PageGrid>
        {items.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} className="group">
            <BrutalCard className="flex min-h-32 flex-col justify-between transition-transform group-hover:-translate-y-1 group-hover:bg-raised">
              <div className="flex items-center justify-between">
                <Icon className="size-7 text-purple" aria-hidden="true" />
                <ArrowUpRight className="size-5" aria-hidden="true" />
              </div>
              <div>
                <h2 className="text-xl font-semibold">{label}</h2>
              </div>
            </BrutalCard>
          </Link>
        ))}
      </PageGrid>
    </div>
  );
}
