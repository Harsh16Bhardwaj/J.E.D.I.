"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, ShieldCheck } from "lucide-react";

import { Sidebar } from "@/components/sidebar";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

export function TopBar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b-2 border-foreground bg-background px-4 sm:px-6 lg:px-8">
      <div className="flex items-center gap-3">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger
            render={
              <Button
                variant="outline"
                size="icon"
                className="rounded-[3px] border-2 lg:hidden"
                aria-label="Open navigation"
              />
            }
          >
            <Menu className="size-4" />
          </SheetTrigger>
          <SheetContent
            side="left"
            className="w-[290px] border-r-2 border-foreground bg-sidebar p-0"
          >
            <SheetTitle className="sr-only">JEDI navigation</SheetTitle>
            <Sidebar onNavigate={() => setOpen(false)} />
          </SheetContent>
        </Sheet>
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
          Job command center
        </span>
      </div>

      <div className="flex items-center gap-3">
        <span className="hidden items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-widest text-acid sm:flex">
          <ShieldCheck className="size-4" aria-hidden="true" />
          Private system
        </span>
        <Link
          href="/login"
          className="rounded-[3px] border-2 border-foreground bg-purple px-3 py-2 font-mono text-[10px] font-bold uppercase tracking-wider text-background shadow-[3px_3px_0_0_var(--foreground)] transition-transform hover:-translate-y-0.5"
        >
          Access
        </Link>
      </div>
    </header>
  );
}
