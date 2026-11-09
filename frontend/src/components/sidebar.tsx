"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Archive, ChevronDown, LogOut } from "lucide-react";
import { toast } from "sonner";
import { useSWRConfig } from "swr";

import {
  currentNavigation,
  allNavigation,
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
import Image from "next/image";

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
  const current = currentNavigation(pathname, allNavigation);

  return (
    <div>
      <p className="workspace-nav-label">{label}</p>
      <nav className="space-y-1" aria-label={label}>
        {items.map(({ href, label: itemLabel, icon: Icon }) => {
          const active = current?.href === href;
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
                "workspace-nav-link",
                active && "is-active",
                tutorialIsNew && !active && "has-update",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              <span>{itemLabel}</span>
              {tutorialIsNew && <span className="workspace-new">New</span>}
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
  const legacyActive = Boolean(currentNavigation(pathname, miscNavigation));
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
    <div className="workspace-sidebar">
      <Link href="/dashboard" className="workspace-brand" onClick={onNavigate}>
        <Image
          src="/logo.png"
          alt=""
          width={36}
          height={40}
          className="h-10 w-9 object-contain"
        />
        <span>
          JEDI<span className="text-acid">.</span>
          <small>WORKSPACE</small>
        </span>
      </Link>

      <div className="workspace-nav-groups">
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
          <details
            key={legacyActive ? "active" : "closed"}
            open={legacyActive}
            className="workspace-legacy"
          >
            <summary>
              <Archive size={15} /> Legacy archive <ChevronDown size={14} />
            </summary>
            <NavigationGroup
              label="Legacy"
              items={miscItems}
              onNavigate={onNavigate}
              tutorialViewed={tutorialViewed}
            />
          </details>
        )}
      </div>

      <div className="workspace-identity">
        <div className="workspace-avatar" aria-hidden="true">
          {groupName.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{groupName}</p>
          <p className="mt-1 text-xs text-muted-foreground">{role} workspace</p>
        </div>
        <Button
          variant="outline"
          size="icon"
          className="shrink-0 cursor-pointer border-transparent text-muted-foreground hover:bg-coral/10 hover:text-coral"
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
