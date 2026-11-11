"use client";

import { useState } from "react";
import { Menu } from "lucide-react";

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

  return (
    <div className="fixed left-4 top-4 z-40 lg:hidden">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger
          render={
            <Button
              variant="outline"
              size="icon"
              className="rounded-lg border-2 bg-background/95 shadow-lg backdrop-blur"
              aria-label="Open navigation"
            />
          }
        >
          <Menu className="size-4" />
        </SheetTrigger>
        <SheetContent side="left" className="w-[290px] border-r border-border bg-sidebar p-0">
          <SheetTitle className="sr-only">JEDI navigation</SheetTitle>
          <Sidebar user={user} onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
    </div>
  );
}
