"use client";

import { useState } from "react";
import { X } from "lucide-react";

import { Input } from "@/components/ui/input";

export function TagField({
  id,
  label,
  values,
  suggestions,
  placeholder,
  error,
  onChange,
}: {
  id: string;
  label: string;
  values: string[];
  suggestions: string[];
  placeholder: string;
  error?: string;
  onChange: (values: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const keys = new Set(values.map((value) => value.toLocaleLowerCase()));

  function add(raw: string) {
    const additions = raw
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    if (!additions.length) return;
    const next = [...values];
    const nextKeys = new Set(keys);
    for (const value of additions) {
      const key = value.toLocaleLowerCase();
      if (!nextKeys.has(key)) {
        next.push(value);
        nextKeys.add(key);
      }
    }
    onChange(next);
    setDraft("");
  }

  return (
    <fieldset>
      <legend className="ops-label">{label}</legend>
      <div className="mt-2">
        <Input
          id={id}
          value={draft}
          placeholder={placeholder}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : undefined}
          className="min-h-11 border-border bg-card aria-invalid:border-coral/60"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === ",") {
              event.preventDefault();
              add(draft);
            }
          }}
          onBlur={() => add(draft)}
        />
      </div>
      {error ? <p id={`${id}-error`} className="mt-2 text-xs text-coral">{error}</p> : null}
      {values.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2" aria-label={`Selected ${label.toLowerCase()}`}>
          {values.map((value) => (
            <button
              key={value.toLocaleLowerCase()}
              type="button"
              onClick={() => onChange(values.filter((item) => item !== value))}
              className="inline-flex min-h-9 items-center gap-2 rounded-full border border-border bg-raised px-3 text-xs hover:border-coral/50"
            >
              {value}<X className="size-3" />
            </button>
          ))}
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {suggestions.filter((item) => !keys.has(item.toLocaleLowerCase())).slice(0, 8).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => add(item)}
            className="min-h-8 rounded-full border border-border/70 px-3 font-mono text-[10px] uppercase tracking-wide text-muted-foreground hover:border-purple/50 hover:text-foreground"
          >
            + {item}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
