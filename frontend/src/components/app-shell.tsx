"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { MotionConfig } from "motion/react";
import useSWR, {
  type Cache,
  type State,
  SWRConfig,
  useSWRConfig,
} from "swr";

import { Sidebar } from "@/components/sidebar";
import { MobileNavigation } from "@/components/top-bar";
import { Button } from "@/components/ui/button";
import { apiGet, ApiError, type User } from "@/lib/api";
import { onboardingRedirect } from "@/lib/public-session";

const publicRoutes = new Set(["/", "/login", "/register"]);
const refreshCacheKey = "jedi:swr-refresh-cache:v1";
const refreshCacheTtlMs = 5 * 60 * 1_000;

type StoredRefreshCache = {
  savedAt: number;
  entries: Array<[string, State<unknown>]>;
};

class RefreshPersistentCache implements Cache<unknown> {
  private readonly values = new Map<string, State<unknown>>();
  private persistTimer: number | undefined;

  constructor() {
    if (typeof window === "undefined") return;
    try {
      const raw = window.sessionStorage.getItem(refreshCacheKey);
      if (!raw) return;
      const stored = JSON.parse(raw) as StoredRefreshCache;
      if (Date.now() - stored.savedAt > refreshCacheTtlMs) {
        window.sessionStorage.removeItem(refreshCacheKey);
        return;
      }
      stored.entries.forEach(([key, value]) => this.values.set(key, value));
    } catch {
      window.sessionStorage.removeItem(refreshCacheKey);
    }
  }

  keys() {
    return this.values.keys();
  }

  get(key: string) {
    return this.values.get(key);
  }

  set(key: string, value: State<unknown>) {
    this.values.set(key, value);
    this.schedulePersist();
  }

  delete(key: string) {
    this.values.delete(key);
    this.schedulePersist();
  }

  private schedulePersist() {
    if (typeof window === "undefined") return;
    if (this.persistTimer !== undefined) window.clearTimeout(this.persistTimer);
    this.persistTimer = window.setTimeout(() => this.persist(), 50);
  }

  private persist() {
    const entries = Array.from(this.values.entries())
      .filter(([, value]) => value.data !== undefined && value.error === undefined)
      .map(([key, value]) => [key, { data: value.data }] as [string, State<unknown>]);
    try {
      window.sessionStorage.setItem(
        refreshCacheKey,
        JSON.stringify({ savedAt: Date.now(), entries } satisfies StoredRefreshCache),
      );
    } catch {
      window.sessionStorage.removeItem(refreshCacheKey);
    }
  }
}

function ProtectedShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { cache } = useSWRConfig();
  const { data: user, error, isLoading, mutate } = useSWR<User>(
    "/api/auth/session",
  );

  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) {
      Array.from(cache.keys()).forEach((key) => cache.delete(key));
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    const destination = onboardingRedirect(user, pathname);
    if (destination) router.replace(destination);
  }, [cache, error, pathname, router, user]);

  const redirecting = Boolean(onboardingRedirect(user, pathname));

  if (
    isLoading ||
    redirecting ||
    (error instanceof ApiError && error.status === 401)
  ) {
    return (
      <main className="grid min-h-screen place-items-center bg-background">
        <div className="text-center">
          <div className="mx-auto size-10 animate-spin border-2 border-acid border-t-transparent" />
          <p className="mt-4 font-mono text-xs uppercase tracking-[0.24em] text-muted-foreground">
            Verifying private session
          </p>
        </div>
      </main>
    );
  }

  if (pathname === "/onboarding") {
    return <div className="min-h-screen bg-background">{children}</div>;
  }

  if (error) {
    return (
      <main className="grid min-h-screen place-items-center p-6">
        <section className="max-w-lg rounded-xl border border-coral/40 bg-card p-7">
          <p className="font-mono text-xs font-bold uppercase tracking-widest text-coral">
            Access check failed
          </p>
          <h1 className="mt-3 text-3xl font-black uppercase">
            The backend did not answer.
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Start the FastAPI server, then retry. Your browser has not been
            treated as logged out.
          </p>
          <Button className="mt-6 min-h-11" onClick={() => void mutate()}>
            Retry session check
          </Button>
        </section>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 hidden w-72 border-r border-border lg:block">
        <Sidebar user={user!} />
      </aside>
      <div className="lg:pl-72">
        <MobileNavigation user={user!} />
        <main className="min-h-screen overflow-hidden px-4 pb-8 pt-20 sm:px-6 lg:px-10 lg:py-12">
          {children}
        </main>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [refreshCache] = useState<Cache<unknown>>(
    () => new RefreshPersistentCache(),
  );
  return (
    <MotionConfig reducedMotion="user">
      <SWRConfig
        value={{
          provider: () => refreshCache,
          fetcher: apiGet,
          dedupingInterval: 10_000,
          keepPreviousData: true,
          revalidateOnFocus: true,
          shouldRetryOnError: (error) =>
            !(error instanceof ApiError) ||
            error.status === 0 ||
            error.status >= 500,
          errorRetryCount: 2,
        }}
      >
        {publicRoutes.has(pathname) ? (
          <div className="min-h-screen bg-background">{children}</div>
        ) : (
          <ProtectedShell>{children}</ProtectedShell>
        )}
      </SWRConfig>
    </MotionConfig>
  );
}
