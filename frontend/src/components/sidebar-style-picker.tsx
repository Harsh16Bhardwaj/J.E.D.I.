"use client";

import {
  createContext,
  useContext,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { Button } from "@/components/ui/button";

const styles = [
  {
    id: "classic",
    name: "Original",
    description: "Bold labels · lime accents",
    color: "#a8c67a",
  },
  {
    id: "minimal",
    name: "Minimal",
    description: "Quiet rows · thin indicator",
    color: "#dddcd6",
  },
  {
    id: "indigo",
    name: "Indigo",
    description: "Violet selection · soft depth",
    color: "#b8a0fa",
  },
  {
    id: "paper",
    name: "Paper",
    description: "Light panel · dark typography",
    color: "#eae7dc",
  },
] as const;
type SidebarStyle = (typeof styles)[number]["id"];
const key = "jedi:sidebar-style:v1";
const changeEvent = "jedi:sidebar-style-change";
function readStyle(): SidebarStyle {
  try {
    const value = localStorage.getItem(key);
    return styles.find((style) => style.id === value)?.id ?? "classic";
  } catch {
    return "classic";
  }
}
function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener(changeEvent, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(changeEvent, callback);
  };
}
const StyleContext = createContext<{
  style: SidebarStyle;
  saved: SidebarStyle;
  preview: SidebarStyle | null;
  setPreview: (style: SidebarStyle | null) => void;
}>({ style: "classic", saved: "classic", preview: null, setPreview: () => {} });

export function SidebarStyleProvider({ children }: { children: ReactNode }) {
  const saved = useSyncExternalStore(
    subscribe,
    readStyle,
    () => "classic" as const,
  );
  const [preview, setPreview] = useState<SidebarStyle | null>(null);
  return (
    <StyleContext.Provider
      value={{ style: preview ?? saved, saved, preview, setPreview }}
    >
      {children}
    </StyleContext.Provider>
  );
}
export function useSidebarStyle() {
  return useContext(StyleContext).style;
}

export function SidebarStylePicker() {
  const { style, saved, preview, setPreview } = useContext(StyleContext);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  return (
    <section
      aria-label="Sidebar appearance"
      className="rounded-xl border border-border bg-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Sidebar styles</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {open
              ? "Preview an option, then keep your favourite."
              : `${styles.find((option) => option.id === saved)?.name} selected`}
          </p>
        </div>
        {!open && (
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
            Change style
          </Button>
        )}
      </div>
      {open && (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4">
            {styles.map((option) => (
              <button
                key={option.id}
                type="button"
                aria-pressed={style === option.id}
                onClick={() => {
                  setPreview(option.id);
                  setError("");
                }}
                className={`flex min-h-16 items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors ${style === option.id ? "border-acid bg-acid/10" : "border-border hover:bg-muted"}`}
              >
                <span
                  aria-hidden="true"
                  className="size-5 shrink-0 rounded border border-black/20"
                  style={{ backgroundColor: option.color }}
                />
                <span className="text-sm font-medium">
                  {option.name}
                  <span className="mt-1 block text-[11px] font-normal text-muted-foreground">
                    {option.description}
                  </span>
                </span>
              </button>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={!preview}
              onClick={() => {
                try {
                  localStorage.setItem(key, style);
                  window.dispatchEvent(new Event(changeEvent));
                  setPreview(null);
                  setOpen(false);
                  setError("");
                } catch {
                  setError(
                    "Your browser could not save the style. The preview is still available.",
                  );
                }
              }}
            >
              Keep this style
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setPreview(null);
                setOpen(false);
                setError("");
              }}
            >
              Discard previews
            </Button>
            {preview && (
              <span role="status" className="text-xs text-muted-foreground">
                Previewing{" "}
                {styles.find((option) => option.id === preview)?.name}
              </span>
            )}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground lg:hidden">
            Open the navigation menu to see the preview.
          </p>
        </>
      )}
      {error && (
        <p role="alert" className="mt-2 text-xs text-coral">
          {error}
        </p>
      )}
    </section>
  );
}
