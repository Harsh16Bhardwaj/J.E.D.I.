import type { LucideIcon } from "lucide-react";

import { BrutalCard } from "@/components/brutal-card";

export function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
}) {
  return (
    <BrutalCard className="flex min-h-64 flex-col items-start justify-end bg-raised">
      <Icon className="mb-auto size-10 text-acid" aria-hidden="true" />
      <h2 className="text-2xl font-black uppercase tracking-tight">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
        {description}
      </p>
    </BrutalCard>
  );
}
