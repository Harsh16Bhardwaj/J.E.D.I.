import type { LucideIcon } from "lucide-react";

import { BrutalCard } from "@/components/brutal-card";
import { cn } from "@/lib/utils";

type StatTileProps = {
  label: string;
  value: string;
  note: string;
  icon: LucideIcon;
  accent?: "acid" | "purple" | "coral";
};

const accents = {
  acid: "bg-acid text-background",
  purple: "bg-purple text-background",
  coral: "bg-coral text-background",
};

export function StatTile({
  label,
  value,
  note,
  icon: Icon,
  accent = "acid",
}: StatTileProps) {
  return (
    <BrutalCard className="flex min-h-44 flex-col justify-between">
      <div className="flex items-start justify-between gap-4">
        <span className="font-mono text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
          {label}
        </span>
        <span
          className={cn(
            "grid size-9 place-items-center rounded-[3px] border-2 border-foreground",
            accents[accent],
          )}
        >
          <Icon className="size-4" aria-hidden="true" />
        </span>
      </div>
      <div>
        <p className="text-4xl font-black tracking-[-0.05em]">{value}</p>
        <p className="mt-2 text-sm text-muted-foreground">{note}</p>
      </div>
    </BrutalCard>
  );
}
