import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function BrutalCard({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card p-5",
        className,
      )}
      {...props}
    />
  );
}
