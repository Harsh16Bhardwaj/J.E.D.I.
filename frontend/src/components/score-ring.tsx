export function ScoreRing({ score }: { score: number | null }) {
  const value =
    score !== null && Number.isFinite(score)
      ? Math.max(0, Math.min(100, score))
      : null;
  return (
    <div
      className="score-ring"
      role="img"
      aria-label={
        value === null
          ? "Preference score unavailable"
          : `Preference score ${value.toFixed(1)} out of 100`
      }
    >
      <svg viewBox="0 0 68 68" aria-hidden="true">
        <circle
          cx="34"
          cy="34"
          r="28"
          fill="none"
          stroke="var(--border)"
          strokeWidth="3"
        />
        {value !== null && (
          <circle
            cx="34"
            cy="34"
            r="28"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={`${(value / 100) * 175.93} 175.93`}
            transform="rotate(-90 34 34)"
          />
        )}
      </svg>
      <strong>{value === null ? "—" : value.toFixed(1)}</strong>
    </div>
  );
}
