"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { ArrowUpRight, KeyRound } from "lucide-react";
import useSWR from "swr";

import type { User } from "@/lib/api";
import { publicSessionMode } from "@/lib/public-session";
import { cn } from "@/lib/utils";

type PublicAuthActionsProps = {
  compact?: boolean;
  className?: string;
};

export function PublicAuthActions({
  compact = false,
  className,
}: PublicAuthActionsProps) {
  const hydrated = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
  const session = useSWR<User>("/api/auth/session", {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  const mode = hydrated
    ? publicSessionMode(session.data, session.isLoading)
    : "loading";
  const height = compact ? "min-h-10" : "min-h-12";

  if (mode === "loading") {
    return (
      <div
        className={cn("flex items-center gap-2", className)}
        aria-label="Checking session"
        aria-busy="true"
      >
        <span className={cn(height, compact ? "w-16" : "w-24", "animate-pulse border border-border bg-raised")} />
        <span className={cn(height, compact ? "w-32" : "w-44", "animate-pulse border border-border bg-raised")} />
      </div>
    );
  }

  if (mode === "authenticated") {
    return (
      <div className={cn("flex items-center", className)}>
        <Link
          href="/dashboard"
          className={cn(
            height,
            "inline-flex items-center gap-2 bg-acid px-4 font-mono text-[11px] font-bold uppercase tracking-[0.08em] text-background transition-colors hover:bg-foreground",
          )}
        >
          Open dashboard <ArrowUpRight className="size-4" aria-hidden="true" />
        </Link>
      </div>
    );
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Link
        href="/login"
        className={cn(
          height,
          "inline-flex items-center border border-border px-4 font-mono text-[11px] font-bold uppercase tracking-[0.08em] transition-colors hover:border-foreground hover:bg-raised",
        )}
      >
        Login
      </Link>
      <Link
        href="/register"
        className={cn(
          height,
          "inline-flex items-center gap-2 bg-acid px-4 font-mono text-[11px] font-bold uppercase tracking-[0.08em] text-background transition-colors hover:bg-foreground",
        )}
      >
        <KeyRound className="size-4" aria-hidden="true" />
        Register with invite
      </Link>
    </div>
  );
}
