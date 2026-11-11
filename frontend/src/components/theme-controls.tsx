"use client";

import { ThemeProvider, useTheme } from "next-themes";
import { useEffect, useSyncExternalStore } from "react";

const themes = ["workspace", "editorial", "spectrum", "carbon"];
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
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  return (
    <label className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 text-xs text-muted-foreground">
      <span aria-hidden="true" className="flex -space-x-1">
        {["var(--primary)", "var(--success)", "var(--warning)"].map((color) => (
          <span
            key={color}
            className="size-2.5 rounded-full ring-2 ring-card"
            style={{ background: color }}
          />
        ))}
      </span>
      <span className="sr-only">Theme</span>
      <select
        aria-label="Theme"
        disabled={!mounted}
        value={mounted && themes.includes(theme ?? "") ? theme : "workspace"}
        onChange={(event) => setTheme(event.target.value)}
        className="min-h-9 cursor-pointer bg-transparent pr-1 text-foreground"
      >
        <option value="workspace">Workspace</option>
        <option value="editorial">Editorial</option>
        <option value="spectrum">Spectrum</option>
        <option value="carbon">Carbon</option>
      </select>
    </label>
  );
}
