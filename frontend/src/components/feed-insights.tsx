/** Counts only displayed, scored recommendations; never implies catalog coverage. */
export function ShortlistDistribution({
  scores,
}: {
  scores: (number | null)[];
}) {
  const valid = scores.filter(
    (score): score is number =>
      score !== null && Number.isFinite(score) && score >= 0 && score <= 100,
  );
  const bands = [
    { label: "80–100", count: valid.filter((score) => score >= 80).length },
    {
      label: "60–79",
      count: valid.filter((score) => score >= 60 && score < 80).length,
    },
    { label: "Below 60", count: valid.filter((score) => score < 60).length },
  ];
  const max = Math.max(1, ...bands.map((band) => band.count));
  return (
    <section aria-labelledby="score-distribution" className="shortlist-insight">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id="score-distribution" className="text-sm font-semibold">
          Score distribution
        </h2>
        <span className="font-mono text-xs">/100</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Within these {scores.length} recommendations
      </p>
      <ul className="my-6 space-y-4">
        {bands.map((band) => (
          <li
            key={band.label}
            className="grid grid-cols-[4rem_1fr_1rem] items-center gap-2 text-xs"
          >
            <span>{band.label}</span>
            <span
              className="h-3 overflow-hidden rounded-sm bg-primary/10"
              aria-hidden="true"
            >
              <span
                className="block h-full rounded-sm bg-primary"
                style={{ width: `${(band.count / max) * 100}%` }}
              />
            </span>
            <strong className="text-right font-mono">{band.count}</strong>
          </li>
        ))}
      </ul>
      <p className="border-t border-border pt-3 text-xs text-muted-foreground">
        {scores.length - valid.length} unscored · Preference alignment
      </p>
    </section>
  );
}

export function ApplicationPipeline({
  counts,
}: {
  counts: Record<string, number>;
}) {
  const order = [
    "NOT_STARTED",
    "PREPARING",
    "APPLIED",
    "SCREENING",
    "ASSESSMENT",
    "INTERVIEW",
    "OFFER",
    "ACCEPTED",
    "REJECTED",
    "WITHDRAWN",
  ];
  const stages = Object.entries(counts)
    .sort(
      ([a], [b]) =>
        (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) -
          (order.indexOf(b) === -1 ? 99 : order.indexOf(b)) ||
        a.localeCompare(b),
    )
    .filter(([, count]) => Number.isFinite(count) && count > 0);
  const total = stages.reduce((sum, [, count]) => sum + count, 0);
  if (!total) return null;
  const colors: Record<string, string> = {
    NOT_STARTED: "#827e6a",
    PREPARING: "var(--purple)",
    APPLIED: "#547578",
    SCREENING: "#647c46",
    ASSESSMENT: "#95712b",
    INTERVIEW: "#476779",
    OFFER: "var(--primary)",
    ACCEPTED: "#294019",
    REJECTED: "var(--coral)",
    WITHDRAWN: "#827e6a",
  };
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div
        className="flex h-3 gap-1 overflow-hidden rounded-sm"
        aria-hidden="true"
      >
        {stages.map(([stage, count]) => (
          <span
            key={stage}
            style={{
              flex: count,
              background: colors[stage] ?? "var(--muted-foreground)",
            }}
          />
        ))}
      </div>
      <ul
        aria-label="Applications by stage"
        className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs"
      >
        {stages.map(([stage, count]) => (
          <li key={stage} className="flex items-center gap-2">
            <span
              className="size-2 rounded-full"
              style={{ background: colors[stage] ?? "var(--muted-foreground)" }}
              aria-hidden="true"
            />
            <span className="capitalize">
              {stage.toLowerCase().replaceAll("_", " ")}
            </span>
            <strong className="font-mono">{count}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}
