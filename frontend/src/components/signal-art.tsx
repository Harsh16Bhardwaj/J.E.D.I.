/** Original lightweight illustrations; no image downloads or canvas runtime. */
export function SignalMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 40 40"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M20 4v32M4 20h32M9 9l22 22M9 31 31 9"
        stroke="currentColor"
        strokeWidth="2"
      />
      <circle
        cx="20"
        cy="20"
        r="6"
        fill="var(--sidebar)"
        stroke="currentColor"
      />
      <path d="m18 17 5 3-5 3Z" fill="currentColor" />
    </svg>
  );
}

export function SignalArt({
  variant = "orbit",
  className = "",
}: {
  variant?: "orbit" | "path";
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 320 210"
      fill="none"
      className={`signal-art ${className}`}
      aria-hidden="true"
    >
      <g stroke="currentColor" strokeOpacity=".17">
        <path d="M0 52h320M0 105h320M0 158h320M53 0v210M106 0v210M160 0v210M213 0v210M267 0v210" />
        <circle cx="160" cy="105" r="84" />
      </g>
      {variant === "orbit" ? (
        <>
          <g className="signal-art-orbit">
            <ellipse
              cx="160"
              cy="105"
              rx="110"
              ry="38"
              transform="rotate(-30 160 105)"
              stroke="currentColor"
              strokeOpacity=".55"
            />
            <ellipse
              cx="160"
              cy="105"
              rx="110"
              ry="38"
              transform="rotate(30 160 105)"
              stroke="currentColor"
              strokeOpacity=".25"
            />
            <circle cx="254" cy="55" r="5" fill="currentColor" />
          </g>
          <circle
            cx="160"
            cy="105"
            r="27"
            fill="var(--card)"
            stroke="currentColor"
            strokeOpacity=".6"
          />
          <path d="m151 105 7 7 13-16" stroke="currentColor" strokeWidth="2" />
        </>
      ) : (
        <>
          <path
            d="M43 153h60c34 0 15-98 56-98h62c30 0 19 73 52 73"
            stroke="currentColor"
            strokeOpacity=".5"
            strokeWidth="1.5"
            strokeDasharray="4 5"
          />
          <circle
            cx="43"
            cy="153"
            r="7"
            fill="var(--card)"
            stroke="currentColor"
          />
          <circle
            cx="159"
            cy="55"
            r="13"
            fill="var(--card)"
            stroke="currentColor"
          />
          <circle cx="159" cy="55" r="4" fill="currentColor" />
          <path
            d="m267 118 11 10-11 10"
            stroke="currentColor"
            strokeWidth="2"
          />
          <path
            d="M89 178h34M198 33h34"
            stroke="currentColor"
            strokeOpacity=".3"
          />
        </>
      )}
      <g fill="currentColor" opacity=".5">
        <circle cx="54" cy="53" r="2" />
        <circle cx="267" cy="158" r="2" />
      </g>
    </svg>
  );
}
