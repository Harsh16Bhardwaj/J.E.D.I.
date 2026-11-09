"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Search } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { searchNavigation } from "@/lib/navigation";
import type { User } from "@/lib/api";

export function CommandMenu({ user }: { user: User }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const router = useRouter();
  const items = searchNavigation(query, user);
  const activeIndex = Math.min(selected, Math.max(0, items.length - 1));

  function changeOpen(value: boolean) {
    setOpen(value);
    if (value) {
      setQuery("");
      setSelected(0);
    }
  }

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        // Leave other dialogs' keyboard handling intact.
        if (!open && document.querySelector('[role="dialog"]')) return;
        event.preventDefault();
        setOpen((value) => !value);
        setQuery("");
        setSelected(0);
      }
    };
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [open]);

  useEffect(() => {
    if (open)
      document
        .getElementById(`${listId}-${activeIndex}`)
        ?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, listId, open, query]);

  function navigate(href: string) {
    setOpen(false);
    router.push(href);
  }

  return (
    <>
      <button
        className="workspace-search"
        onClick={() => changeOpen(true)}
        aria-label="Go to a page"
        aria-keyshortcuts="Control+k Meta+k"
      >
        <Search size={15} />
        <span>Go to…</span>
        <kbd>⌘ / Ctrl K</kbd>
      </button>
      <Dialog open={open} onOpenChange={changeOpen}>
        <DialogContent
          className="command-dialog sm:max-w-xl"
          initialFocus={input}
        >
          <DialogHeader>
            <DialogTitle>Where to next?</DialogTitle>
            <DialogDescription>
              Find a page in your workspace.
            </DialogDescription>
          </DialogHeader>
          <div className="command-search">
            <Search size={18} />
            <input
              ref={input}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setSelected(0);
              }}
              placeholder="Search pages…"
              aria-label="Search pages"
              role="combobox"
              aria-autocomplete="list"
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={
                items.length ? `${listId}-${activeIndex}` : undefined
              }
              onKeyDown={(event) => {
                if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                  event.preventDefault();
                  setSelected(
                    items.length
                      ? (activeIndex +
                          (event.key === "ArrowDown" ? 1 : -1) +
                          items.length) %
                          items.length
                      : 0,
                  );
                }
                if (event.key === "Enter" && items[activeIndex]) {
                  event.preventDefault();
                  navigate(items[activeIndex].href);
                }
              }}
            />
          </div>
          <div
            id={listId}
            role="listbox"
            aria-label="Workspace pages"
            className="command-results"
          >
            {items.map(({ href, label, icon: Icon }, index) => (
              <button
                key={href}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                tabIndex={-1}
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setSelected(index)}
                onClick={() => navigate(href)}
              >
                <Icon size={17} />
                <span>
                  {label}
                  <small>{href}</small>
                </span>
                <ArrowUpRight size={15} />
              </button>
            ))}
          </div>
          {!items.length && (
            <p className="command-empty" role="status">
              No pages match “{query}”. Try jobs, learning, or applications.
            </p>
          )}
          <p className="command-hint">
            <span>↑ ↓ to explore</span>
            <span>↵ to open</span>
            <span>Esc to close</span>
          </p>
        </DialogContent>
      </Dialog>
    </>
  );
}
