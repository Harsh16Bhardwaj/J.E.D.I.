"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ChevronDown, LogOut } from "lucide-react";
import { toast } from "sonner";
import { useSWRConfig } from "swr";

import {
  currentNavigation,
  adminNavigation,
  primaryNavigation,
  miscNavigation,
  settingsNavigation,
  visibleNavigation,
  type NavigationItem,
} from "@/lib/navigation";
import { apiRequest, errorSummary, type User } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  hasCompletedTutorial,
  TUTORIAL_COMPLETE_EVENT,
} from "@/lib/tutorial-state";
import { cn } from "@/lib/utils";

function NavigationGroup({
  label,
  items,
  onNavigate,
  tutorialViewed,
}: {
  label: string;
  items: readonly NavigationItem[];
  onNavigate?: () => void;
  tutorialViewed: boolean | null;
}) {
  const pathname = usePathname();

  return (
    <div>
      <p className="mb-2 px-3 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
        {label}
      </p>
      <nav className="space-y-1" aria-label={label}>
        {items.map(({ href, label: itemLabel, icon: Icon }) => {
          const active = currentNavigation(pathname)?.href === href;
          const tutorialIsNew =
            href === "/tutorial" && tutorialViewed === false;

          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              aria-label={tutorialIsNew ? `${itemLabel}, new` : undefined}
              className={cn(
                "flex min-h-10 items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                "text-muted-foreground hover:bg-muted hover:text-foreground",
                active && "bg-sidebar-accent text-sidebar-accent-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              <span>{itemLabel}</span>
              {tutorialIsNew && (
                <span className="ml-auto size-1.5 rounded-full bg-purple">
                  <span className="sr-only">New</span>
                </span>
              )}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

export function Sidebar({
  user,
  onNavigate,
}: {
  user: User;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const [tutorialViewed, setTutorialViewed] = useState<boolean | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const groupName = user.group?.name ?? "JEDI group";
  const role = user.isGroupOwner ? "Owner" : "Member";

  useEffect(() => {
    const syncTutorialState = () =>
      setTutorialViewed(hasCompletedTutorial(window.localStorage));

    syncTutorialState();
    window.addEventListener(TUTORIAL_COMPLETE_EVENT, syncTutorialState);
    window.addEventListener("storage", syncTutorialState);
    return () => {
      window.removeEventListener(TUTORIAL_COMPLETE_EVENT, syncTutorialState);
      window.removeEventListener("storage", syncTutorialState);
    };
  }, []);

  const adminItems = visibleNavigation(adminNavigation, user);
  const primaryItems = visibleNavigation(primaryNavigation, user);
  const settingsItems = visibleNavigation(settingsNavigation, user);
  const miscItems = visibleNavigation(miscNavigation, user);

  async function logout() {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await apiRequest<void>("/api/auth/logout", { method: "POST" });
      await mutate(() => true, undefined, { revalidate: false });
      toast.success("Private session closed.");
      router.replace("/login");
      onNavigate?.();
    } catch (error) {
      toast.error(errorSummary(error));
      setLoggingOut(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col bg-sidebar px-4 py-6">
      <Link
        href="/dashboard"
        className="mb-7 block px-2 pt-1"
        onClick={onNavigate}
      >
        <span className="flex items-center gap-2">
          <Image
            src="/logo.png"
            alt=""
            width={32}
            height={36}
            className="h-9 w-8 shrink-0 object-contain"
            priority
          />
          <span className="text-3xl font-black tracking-[-0.08em]">JEDI/</span>
        </span>
        <span className="mt-1 block font-mono text-[9px] uppercase tracking-[0.24em] text-muted-foreground">
          Job intelligence
        </span>
      </Link>

      <div className="space-y-6">
        <NavigationGroup
          label="Daily signal"
          items={primaryItems}
          onNavigate={onNavigate}
          tutorialViewed={tutorialViewed}
        />
        <NavigationGroup
          label="Group workspace"
          items={settingsItems}
          onNavigate={onNavigate}
          tutorialViewed={tutorialViewed}
        />
        {adminItems.length > 0 && (
          <NavigationGroup
            label="Admin"
            items={adminItems}
            onNavigate={onNavigate}
            tutorialViewed={tutorialViewed}
          />
        )}
        {miscItems.length > 0 && (
          <details
            key={currentNavigation(pathname, miscNavigation)?.href ?? "closed"}
            open={Boolean(currentNavigation(pathname, miscNavigation))}
            className="group"
          >
            <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between px-3 text-[10px] font-medium uppercase tracking-widest text-muted-foreground [&::-webkit-details-marker]:hidden">
              Legacy{" "}
              <ChevronDown
                className="size-3 transition-transform group-open:rotate-180"
                aria-hidden="true"
              />
            </summary>
            <NavigationGroup
              label="Legacy tools"
              items={miscItems}
              onNavigate={onNavigate}
              tutorialViewed={tutorialViewed}
            />
          </details>
        )}
      </div>

      <div className="mt-auto flex items-center gap-3 border-t border-border pt-4">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{groupName}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {user.isGroupOwner ? "Admin" : role}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="shrink-0 text-muted-foreground hover:text-coral"
          disabled={loggingOut}
          aria-label={loggingOut ? "Logging out" : "Logout"}
          title={loggingOut ? "Logging out" : "Logout"}
          onClick={() => void logout()}
        >
          <LogOut className="size-4" />
          <span className="sr-only">
            {loggingOut ? "Logging out" : "Logout"}
          </span>
        </Button>
      </div>
    </div>
  );
}
