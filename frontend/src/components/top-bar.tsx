"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  currentNavigation,
  visibleNavigation,
  allNavigation,
} from "@/lib/navigation";
import { CommandMenu } from "@/components/command-menu";
import { SignalMark } from "@/components/signal-art";
import { ChevronRight, Menu } from "lucide-react";

import { Sidebar } from "@/components/sidebar";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { User } from "@/lib/api";

export function MobileNavigation({ user }: { user: User }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const current = currentNavigation(
    pathname,
    visibleNavigation(allNavigation, user),
  );

  return (
    <header className="workspace-topbar">
      <a href="#workspace-content" className="workspace-skip">
        Skip to page content
      </a>
      <div className="lg:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger
            render={
              <Button
                variant="outline"
                size="icon"
                className="border-transparent bg-transparent"
                aria-label="Open navigation"
              />
            }
          >
            <Menu className="size-4" />
          </SheetTrigger>
          <SheetContent
            side="left"
            className="w-[290px] max-w-[90vw] overflow-y-auto border-r border-border bg-sidebar p-0"
          >
            <SheetTitle className="sr-only">JEDI navigation</SheetTitle>
            <Sidebar user={user} onNavigate={() => setOpen(false)} />
          </SheetContent>
        </Sheet>
      </div>
      <div className="workspace-breadcrumb">
        <Link href="/dashboard" aria-label="JEDI dashboard">
          <SignalMark className="size-5" />
          <span>Workspace</span>
        </Link>
        <ChevronRight size={12} />
        <span>{current?.label ?? "Workspace"}</span>
      </div>
      <CommandMenu user={user} />
    </header>
  );
}
