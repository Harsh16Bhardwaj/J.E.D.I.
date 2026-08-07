"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";
import { toast } from "sonner";
import { useSWRConfig } from "swr";

import {
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
      <p className="mb-2 px-3 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </p>
      <nav className="space-y-1" aria-label={label}>
        {items.map(({ href, label: itemLabel, icon: Icon }) => {
          const active =
            pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));
          const tutorialIsNew = href === "/tutorial" && tutorialViewed === false;

          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              aria-label={tutorialIsNew ? `${itemLabel}, new` : undefined}
              className={cn(
                "flex items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 font-mono text-xs font-bold uppercase tracking-wide transition-[background-color,color]",
                "hover:border-border hover:bg-raised",
                active &&
                  "border-acid/25 bg-acid/10 text-acid",
                tutorialIsNew && !active && "border-purple/30 bg-purple/10 text-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              <span>{itemLabel}</span>
              {tutorialIsNew && (
                <span className="ml-auto rounded-full bg-purple px-2 py-0.5 text-[9px] text-background">
                  New
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
    <div className="flex h-full flex-col bg-sidebar p-4">
      <Link href="/dashboard" className="mb-7 block px-2 pt-1" onClick={onNavigate}>
        <span className="flex items-center gap-2">
          <Image
            src="/logo.png"
            alt=""
            width={50}
            height={56}
            className="h-14 w-[50px] shrink-0 object-contain"
            priority
          />
          <span className="text-4xl font-black tracking-[-0.08em]">JEDI/</span>
        </span>
        <span className="mt-1 block font-mono text-[9px] uppercase tracking-[0.24em] text-muted-foreground">
          Job intelligence
        </span>
      </Link>

      <div className="space-y-8">
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
        {miscItems.length > 0 && (
          <NavigationGroup
            label="Model room"
            items={miscItems}
            onNavigate={onNavigate}
            tutorialViewed={tutorialViewed}
          />
        )}
      </div>

      <div className="mt-auto border-t border-border pt-4">
        <div className="flex items-center justify-between gap-3">
          <p className="truncate text-sm font-semibold">{groupName}</p>
          <span className="border border-acid/30 bg-acid/10 px-2 py-1 font-mono text-[9px] font-bold uppercase tracking-widest text-acid">
            {role}
          </span>
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          One shared profile, model, and daily ranked feed.
        </p>
        <Button
          variant="outline"
          size="icon"
          className="mt-3 ml-auto flex cursor-pointer hover:border-coral/40 hover:bg-coral/10 hover:text-coral"
          disabled={loggingOut}
          aria-label={loggingOut ? "Logging out" : "Logout"}
          title={loggingOut ? "Logging out" : "Logout"}
          onClick={() => void logout()}
        >
          <LogOut className="size-4" />
          <span className="sr-only">{loggingOut ? "Logging out" : "Logout"}</span>
        </Button>
      </div>
    </div>
  );
}
