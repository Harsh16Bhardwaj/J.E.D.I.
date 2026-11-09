export function JediSentinel() {
  return (
    <svg
      viewBox="0 0 640 720"
      fill="none"
      role="img"
      aria-label="An original hooded sentinel holding a jade beam of light, surrounded by orbital rings"
      className="jedi-sentinel"
    >
      <defs>
        <radialGradient id="sentinel-aura">
          <stop stopColor="#80ffc6" stopOpacity=".23" />
          <stop offset="1" stopColor="#0b1512" stopOpacity="0" />
        </radialGradient>
        <linearGradient
          id="sentinel-cloak"
          x1="220"
          y1="220"
          x2="440"
          y2="660"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#5b7166" />
          <stop offset=".38" stopColor="#233d33" />
          <stop offset="1" stopColor="#080e0c" />
        </linearGradient>
        <linearGradient
          id="sentinel-hood"
          x1="260"
          y1="220"
          x2="392"
          y2="375"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#8fae99" />
          <stop offset=".45" stopColor="#3c5448" />
          <stop offset="1" stopColor="#12251e" />
        </linearGradient>
        <linearGradient
          id="sentinel-saber"
          x1="150"
          y1="170"
          x2="220"
          y2="480"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#f1fff5" />
          <stop offset="1" stopColor="#8effc7" />
        </linearGradient>
        <filter id="sentinel-glow">
          <feGaussianBlur stdDeviation="7" />
        </filter>
        <filter id="sentinel-soft">
          <feGaussianBlur stdDeviation="22" />
        </filter>
      </defs>
      <ellipse cx="325" cy="370" rx="290" ry="310" fill="url(#sentinel-aura)" />
      <g className="sentinel-orbits" stroke="#9dddb7" strokeOpacity=".2">
        <circle cx="320" cy="345" r="243" strokeDasharray="2 9" />
        <ellipse
          cx="320"
          cy="345"
          rx="290"
          ry="105"
          transform="rotate(-38 320 345)"
        />
        <ellipse
          cx="320"
          cy="345"
          rx="280"
          ry="137"
          transform="rotate(40 320 345)"
        />
        <path
          d="M77 345a243 243 0 0 1 243-243"
          stroke="#b2ebca"
          strokeOpacity=".6"
        />
        <circle cx="512" cy="198" r="4" fill="#c6ffde" stroke="none" />
        <circle cx="92" cy="425" r="3" fill="#c6ffde" stroke="none" />
      </g>
      <g stroke="#77a58b" strokeOpacity=".22">
        <path d="M320 44v90M320 572v100M30 345h70M540 345h70" />
        <path d="M300 64h40M300 650h40M44 325v40M590 325v40" />
      </g>
      <ellipse
        cx="327"
        cy="641"
        rx="133"
        ry="16"
        fill="#8dffbc"
        opacity=".13"
        filter="url(#sentinel-soft)"
      />
      <g className="sentinel-figure">
        <path
          d="m267 327-44 44-63 243 112-31 39 47 110-13 61-2-66-238-39-46Z"
          fill="url(#sentinel-cloak)"
          stroke="#7caa91"
          strokeOpacity=".35"
        />
        <path
          d="m277 352-35 185-24 60 54-14 42-205Z"
          fill="#637d6c"
          opacity=".5"
        />
        <path
          d="m357 341 26 113 38 163 61-2-66-238Z"
          fill="#07110d"
          opacity=".8"
        />
        <path d="m312 374-13 196 12 60 44-11 9-163-16-87Z" fill="#172a20" />
        <path
          d="m319 380 8 205M285 415l-40 142M376 423l42 150"
          stroke="#92baa1"
          strokeOpacity=".18"
        />
        <path
          d="M260 318c-14-46 13-115 62-131 42 15 72 49 74 118l-38 69-46 15Z"
          fill="url(#sentinel-hood)"
          stroke="#a0c6ad"
          strokeOpacity=".5"
        />
        <path
          d="M322 215c-29 29-42 60-41 99l33 44 43-37c-1-48-14-80-35-106Z"
          fill="#060d0a"
        />
        <path d="m290 292 28-7 27 7-8 33-22 13-19-13Z" fill="#17251d" />
        <path
          d="m295 297 18 3m10 0 17-3"
          stroke="#c1ffda"
          strokeWidth="2"
          opacity=".8"
        />
        <path
          d="m322 215 19 46 16 60-43 37 44 16 38-69"
          fill="#0c1c13"
          opacity=".85"
        />
        <path
          d="m260 318 22 36 30 35 17-17-48-58"
          fill="#8eaa95"
          opacity=".4"
        />
        <path
          d="m256 377-46 61 20 32 55-50M383 397l-31 60-63 7-5-25 47-16 20-43"
          fill="#3d5949"
          stroke="#94c4a5"
          strokeOpacity=".3"
        />
        <path d="m213 439 19-10 21 16-12 25-21-3Z" fill="#8a9d82" />
        <path d="m291 440-18 3-9 17 24 10 10-12" fill="#7e9379" />
        <path
          d="m221 457 12 53"
          stroke="#0b110e"
          strokeWidth="17"
          strokeLinecap="round"
        />
        <path d="m221 458 12 51" stroke="#8f9e90" strokeWidth="8" />
        <path
          d="m220 474 12-3m-10 13 12-3m-9 13 12-3"
          stroke="#283a2d"
          strokeWidth="4"
        />
        <path
          d="m151 163 68 289"
          stroke="#65ffb2"
          strokeWidth="22"
          strokeLinecap="round"
          filter="url(#sentinel-glow)"
          opacity=".7"
        />
        <path
          d="m151 163 68 289"
          stroke="url(#sentinel-saber)"
          strokeWidth="6"
          strokeLinecap="round"
        />
        <path
          d="m152 166 66 283"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </g>
      <g
        fill="#b3d5bf"
        opacity=".6"
        fontFamily="monospace"
        fontSize="9"
        letterSpacing="2"
      >
        <text x="66" y="125">
          SIGNAL / FOUND
        </text>
        <text x="439" y="563">
          YOUR NEXT ORBIT
        </text>
        <text x="262" y="690">
          THE JEDI SENTINEL
        </text>
      </g>
      <g fill="#ccffe0" className="sentinel-stars">
        <circle cx="139" cy="282" r="2" />
        <circle cx="463" cy="354" r="2" />
        <circle cx="418" cy="124" r="1.5" />
        <circle cx="116" cy="532" r="1.5" />
      </g>
    </svg>
  );
}
