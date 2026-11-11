"use client";

import { ThemeProvider, useTheme } from "next-themes";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const themes = [
  "workspace",
  "editorial",
  "spectrum",
  "carbon",
  "ocean",
  "citrus",
  "rosewood",
  "arctic",
  "terminal",
];
const themeMeta = {
  workspace: {
    label: "Workspace",
    note: "Plum + cobalt",
    swatches: ["#321A38", "#1559C5", "#147D52"],
  },
  editorial: {
    label: "Editorial",
    note: "Paper + ink",
    swatches: ["#EEE8DD", "#1B4DA3", "#B14C32"],
  },
  spectrum: {
    label: "Spectrum",
    note: "Violet + teal",
    swatches: ["#6246CA", "#087365", "#B53D70"],
  },
  carbon: {
    label: "Carbon",
    note: "Dark + electric",
    swatches: ["#111215", "#B3A2FF", "#82DAB2"],
  },
  ocean: {
    label: "Ocean",
    note: "Navy + aqua",
    swatches: ["#102A43", "#087E8B", "#F28F3B"],
  },
  citrus: {
    label: "Citrus",
    note: "Graphite + lime",
    swatches: ["#202A25", "#D97706", "#65A30D"],
  },
  rosewood: {
    label: "Rosewood",
    note: "Burgundy + gold",
    swatches: ["#3B1725", "#9F1239", "#B7791F"],
  },
  arctic: {
    label: "Arctic",
    note: "Slate + cyan",
    swatches: ["#E8F1F5", "#2563EB", "#0F766E"],
  },
  terminal: {
    label: "Terminal",
    note: "Ink + phosphor",
    swatches: ["#0B1210", "#39FF88", "#F5C451"],
  },
} as const;
const subscribe = () => () => {};

export function SiteTheme({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="data-theme"
      storageKey="jedi:theme"
      defaultTheme="workspace"
      enableSystem={false}
      themes={themes}
      disableTransitionOnChange
    >
      <ThemeMigration />
      {children}
    </ThemeProvider>
  );
}

function ThemeMigration() {
  const { theme, setTheme } = useTheme();
  useEffect(() => {
    if (theme && !themes.includes(theme)) setTheme("workspace");
  }, [theme, setTheme]);
  return null;
}

export function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  const active =
    mounted && themes.includes(theme ?? "")
      ? (theme as keyof typeof themeMeta)
      : "workspace";
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Choose theme"
        disabled={!mounted}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-border bg-card px-2.5 text-xs text-foreground shadow-sm transition hover:bg-muted"
      >
        <span aria-hidden="true" className="flex -space-x-1">
          {themeMeta[active].swatches.map((color) => (
            <span
              key={color}
              className="size-2.5 rounded-full ring-2 ring-card"
              style={{ background: color }}
            />
          ))}
        </span>
        <span className="hidden sm:inline">{themeMeta[active].label}</span>
        <span aria-hidden="true" className="text-muted-foreground">
          ⌄
        </span>
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Theme choices"
          className="absolute right-0 z-50 mt-2 grid w-[min(21rem,calc(100vw-2rem))] grid-cols-2 gap-1 rounded-xl border border-border bg-popover p-2 text-popover-foreground shadow-xl"
        >
          {themes.map((id) => {
            const meta = themeMeta[id as keyof typeof themeMeta];
            const selected = id === active;
            return (
              <button
                key={id}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                onClick={() => {
                  setTheme(id);
                  setOpen(false);
                }}
                className={`flex items-center gap-2 rounded-lg p-2 text-left transition ${selected ? "bg-accent/10 ring-1 ring-primary/30" : "hover:bg-muted"}`}
              >
                <span aria-hidden="true" className="flex shrink-0 -space-x-1">
                  {meta.swatches.map((color) => (
                    <span
                      key={color}
                      className="size-3 rounded-full ring-2 ring-popover"
                      style={{ background: color }}
                    />
                  ))}
                </span>
                <span className="min-w-0">
                  <span className="block text-xs font-medium">
                    {meta.label}
                    {selected && <span className="ml-1 text-primary">✓</span>}
                  </span>
                  <span className="block truncate text-[10px] text-muted-foreground">
                    {meta.note}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
