"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  primaryNavigation,
  settingsNavigation,
} from "@/lib/navigation";
import { cn } from "@/lib/utils";

function NavigationGroup({
  label,
  items,
  onNavigate,
}: {
  label: string;
  items: typeof primaryNavigation | typeof settingsNavigation;
  onNavigate?: () => void;
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

          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-3 rounded-[3px] border-2 border-transparent px-3 py-2.5 font-mono text-xs font-bold uppercase tracking-wide transition-[background-color,color,transform]",
                "hover:translate-x-1 hover:border-foreground hover:bg-raised",
                active &&
                  "border-foreground bg-acid text-background shadow-[3px_3px_0_0_var(--foreground)]",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              {itemLabel}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-sidebar p-4">
      <Link href="/" className="mb-10 block" onClick={onNavigate}>
        <span className="font-mono text-xs font-bold uppercase tracking-[0.32em] text-acid">
          Personal ops
        </span>
        <span className="mt-1 block text-4xl font-black tracking-[-0.08em]">
          JEDI/
        </span>
      </Link>

      <div className="space-y-8">
        <NavigationGroup
          label="Command center"
          items={primaryNavigation}
          onNavigate={onNavigate}
        />
        <NavigationGroup
          label="Configuration"
          items={settingsNavigation}
          onNavigate={onNavigate}
        />
      </div>

      <div className="mt-auto border-t-2 border-foreground pt-4">
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
          Foundation / v0.1
        </p>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          Contracts are live. Product workflows arrive next.
        </p>
      </div>
    </div>
  );
}
