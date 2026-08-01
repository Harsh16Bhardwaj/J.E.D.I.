import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type StatusTone = "ready" | "queued" | "warning" | "offline";

const tones: Record<StatusTone, string> = {
  ready: "border-acid/30 bg-acid/10 text-acid",
  queued: "border-purple/30 bg-purple/10 text-purple",
  warning: "border-coral/30 bg-coral/10 text-coral",
  offline: "border-border bg-raised text-muted-foreground",
};

export function StatusBadge({
  children,
  tone = "ready",
}: {
  children: React.ReactNode;
  tone?: StatusTone;
}) {
  return (
    <Badge
      className={cn(
        "rounded-full border px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-widest",
        tones[tone],
      )}
    >
      {children}
    </Badge>
  );
}
