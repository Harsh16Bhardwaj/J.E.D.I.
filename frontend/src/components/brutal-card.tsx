import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function BrutalCard({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-[4px] border-2 border-foreground bg-card p-5 shadow-[5px_5px_0_0_var(--foreground)]",
        className,
      )}
      {...props}
    />
  );
}
