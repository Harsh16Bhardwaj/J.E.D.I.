"use client";

import { useId } from "react";

export function CareerEngraving({ className = "" }: { className?: string }) {
  const pattern = useId();
  return (
    <svg
      viewBox="0 0 620 380"
      fill="none"
      className={className}
      role="img"
      aria-label="Editorial illustration of a job brief, resume notes, and a magnifying glass on a paper desk"
    >
      <defs>
        <pattern
          id={pattern}
          width="6"
          height="6"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="1" cy="1" r=".65" fill="#405b22" opacity=".35" />
        </pattern>
      </defs>
      <ellipse cx="305" cy="322" rx="245" ry="23" fill="#d8d2c3" />
      <path d="m78 110 312-37 34 239-312 37Z" fill="#d9d4c5" stroke="#2d3027" />
      <path
        d="m90 99 312-37 28 236-312 37Z"
        fill="#fffdf7"
        stroke="#2d3027"
        strokeWidth="1.5"
      />
      <path d="m111 117 268-32m-266 40 268-32" stroke="#2d3027" />
      <text
        x="122"
        y="150"
        transform="rotate(-7 122 150)"
        fontFamily="Georgia,serif"
        fontSize="27"
        fill="#272720"
      >
        THE NEXT CHAPTER
      </text>
      <path d="m122 168 260-31" stroke="#2d3027" />
      <path d="m128 183 108-13 9 73-108 13Z" fill="#e3e8d8" stroke="#405b22" />
      <path
        d="m138 246 18-30 22 10 28-35 28 42"
        stroke="#405b22"
        strokeWidth="2"
      />
      <circle cx="155" cy="195" r="7" fill="#405b22" />
      <path
        d="m257 169 121-14m-119 25 121-14m-119 25 121-14m-119 25 110-13m-108 24 121-14m-119 25 93-11m-211 49 260-31m-258 43 260-31m-258 43 169-20"
        stroke="#7c7a6c"
      />
      <path
        d="m330 104 147 13-15 185-148-13Z"
        fill="#ede8db"
        stroke="#2d3027"
        strokeWidth="1.5"
      />
      <text
        x="346"
        y="138"
        transform="rotate(5 346 138)"
        fontFamily="monospace"
        fontSize="10"
        letterSpacing="1"
        fill="#405b22"
      >
        YOUR FIELD NOTES
      </text>
      <path
        d="m345 153 111 10m-113 9 111 10m-113 9 111 10m-113 9 90 8"
        stroke="#8d8879"
      />
      <path d="m345 252 23 24 56-58" stroke="#405b22" strokeWidth="5" />
      <path
        d="M453 253 523 330"
        stroke="#292d23"
        strokeWidth="17"
        strokeLinecap="round"
      />
      <path
        d="m456 256 63 69"
        stroke="#665183"
        strokeWidth="9"
        strokeLinecap="round"
      />
      <circle
        cx="420"
        cy="210"
        r="65"
        fill="#f4f1e8"
        fillOpacity=".76"
        stroke="#292d23"
        strokeWidth="4"
      />
      <circle cx="420" cy="210" r="55" stroke="#405b22" />
      <circle cx="420" cy="210" r="48" fill={`url(#${pattern})`} />
      <path d="m396 211 17 17 32-38" stroke="#405b22" strokeWidth="5" />
      <path d="m501 153 18-62 11 65-10 87Z" fill="#405b22" stroke="#292d23" />
      <path
        d="m519 91 6-19 5 84m-13 87-4 21 11-20"
        stroke="#292d23"
        strokeWidth="2"
      />
      <g stroke="#405b22" strokeWidth="1.5">
        <path d="M76 290c-29-29-30-71-17-103m1 25-19-19m16 35-19-8m20 23 18-14m-14 31-19-2m25 15 16-16" />
        <path d="M548 287c20-21 26-55 15-82m3 17 14-14m-12 30 15-8m-18 22-15-12m10 29 14-6" />
      </g>
      <path d="M59 346h493" stroke="#aaa394" />
    </svg>
  );
}
