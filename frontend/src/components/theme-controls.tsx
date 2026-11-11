"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

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
  "nebula",
  "nightshift",
  "afterglow",
  "synthwave",
];
const themeMeta = {
  workspace: {
    label: "Command Center",
    note: "Plum + cobalt",
    swatches: ["#321A38", "#1559C5", "#147D52"],
  },
  editorial: {
    label: "Sunday Paper",
    note: "Paper + ink",
    swatches: ["#EEE8DD", "#1B4DA3", "#B14C32"],
  },
  spectrum: {
    label: "Prism",
    note: "Violet + teal",
    swatches: ["#6246CA", "#087365", "#B53D70"],
  },
  carbon: {
    label: "Black Tie",
    note: "Dark + electric",
    swatches: ["#111215", "#B3A2FF", "#82DAB2"],
  },
  ocean: {
    label: "Tidepool",
    note: "Navy + aqua",
    swatches: ["#102A43", "#087E8B", "#F28F3B"],
  },
  citrus: {
    label: "Fresh Press",
    note: "Graphite + lime",
    swatches: ["#202A25", "#D97706", "#65A30D"],
  },
  rosewood: {
    label: "Velvet Hour",
    note: "Burgundy + gold",
    swatches: ["#3B1725", "#9F1239", "#B7791F"],
  },
  arctic: {
    label: "Cold Front",
    note: "Slate + cyan",
    swatches: ["#E8F1F5", "#2563EB", "#0F766E"],
  },
  terminal: {
    label: "Green Room",
    note: "Ink + phosphor",
    swatches: ["#0B1210", "#39FF88", "#F5C451"],
  },
  nebula: {
    label: "Nebula",
    note: "Indigo + coral",
    swatches: ["#15132B", "#A78BFA", "#FB7185"],
  },
  nightshift: {
    label: "Nightshift",
    note: "Navy + amber",
    swatches: ["#0F1B2D", "#60A5FA", "#FBBF24"],
  },
  afterglow: {
    label: "Afterglow",
    note: "Plum + peach",
    swatches: ["#241522", "#F0A6CA", "#FDBA74"],
  },
  synthwave: {
    label: "Synthwave",
    note: "Violet + neon",
    swatches: ["#180D2E", "#E879F9", "#2DD4BF"],
  },
} as const;
const subscribe = () => () => {};
type ThemeId = (typeof themes)[number];
const ThemeContext = createContext<{
  theme: ThemeId;
  setTheme: (theme: string) => void;
}>({ theme: "workspace", setTheme: () => {} });
const useTheme = () => useContext(ThemeContext);

export function SiteTheme({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>("workspace");
  useEffect(() => {
    const stored = window.localStorage.getItem("jedi:theme");
    setThemeState(
      stored && themes.includes(stored as ThemeId)
        ? (stored as ThemeId)
        : "workspace",
    );
  }, []);
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("jedi:theme", theme);
  }, [theme]);
  const setTheme = (next: string) =>
    setThemeState(
      themes.includes(next as ThemeId) ? (next as ThemeId) : "workspace",
    );
  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
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
