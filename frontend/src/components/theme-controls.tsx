"use client";

import { ThemeProvider, useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { Palette } from "lucide-react";

const themes = ["paper", "studio", "midnight", "forest"];
const subscribe = () => () => {};

export function SiteTheme({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="data-theme"
      storageKey="jedi:theme"
      defaultTheme="paper"
      enableSystem={false}
      themes={themes}
      disableTransitionOnChange
    >
      {children}
    </ThemeProvider>
  );
}

export function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  return (
    <label className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 text-xs text-muted-foreground">
      <Palette className="size-3.5" aria-hidden="true" />
      <span className="sr-only">Theme</span>
      <select
        aria-label="Theme"
        disabled={!mounted}
        value={mounted && themes.includes(theme ?? "") ? theme : "paper"}
        onChange={(event) => setTheme(event.target.value)}
        className="min-h-9 cursor-pointer bg-transparent pr-1 text-foreground"
      >
        <option value="paper">Paper</option>
        <option value="studio">Studio</option>
        <option value="midnight">Midnight</option>
        <option value="forest">Forest</option>
      </select>
    </label>
  );
}
