import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type StatusTone = "ready" | "queued" | "warning" | "offline";

const tones: Record<StatusTone, string> = {
  ready: "bg-acid text-background",
  queued: "bg-purple text-background",
  warning: "bg-coral text-background",
  offline: "bg-raised text-foreground",
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
        "rounded-[3px] border-2 border-foreground px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-widest",
        tones[tone],
      )}
    >
      {children}
    </Badge>
  );
}
