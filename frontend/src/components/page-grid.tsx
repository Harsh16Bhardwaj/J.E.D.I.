import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function PageGrid({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "grid gap-6 md:grid-cols-2 xl:grid-cols-3",
        className,
      )}
      {...props}
    />
  );
}
