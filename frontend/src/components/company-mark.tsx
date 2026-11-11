import type { CSSProperties } from "react";

/** A decorative initial, not an employer's official logo. Stable across sorting. */
export function CompanyMark({ name }: { name: string }) {
  const normalized = name.trim().toLocaleLowerCase("en-US");
  let hash = 0;
  for (const character of normalized)
    hash = (hash * 31 + character.codePointAt(0)!) >>> 0;
  const family = (hash % 6) + 1;
  return (
    <span
      aria-hidden="true"
      className="company-stamp"
      style={
        {
          "--identity-ink": `var(--identity-${family}-ink)`,
          "--identity-bg": `var(--identity-${family}-bg)`,
        } as CSSProperties
      }
    >
      {name.trim().charAt(0).toUpperCase() || "J"}
    </span>
  );
}
