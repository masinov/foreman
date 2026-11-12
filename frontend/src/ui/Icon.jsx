import React from "react";

// One small set, drawn on a 16px grid with one stroke weight, so every icon
// sits on the same line as 13px text. An icon never carries meaning alone:
// it sits beside a word, or its control has an accessible name.
const PATHS = {
  settings: (
    <>
      <path d="M2 4h6.5M12.5 4H14M2 8h1.5M7.5 8H14M2 12h7.5M13.5 12h.5" />
      <circle cx="10.5" cy="4" r="1.75" />
      <circle cx="5.5" cy="8" r="1.75" />
      <circle cx="11.5" cy="12" r="1.75" />
    </>
  ),
  panel: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" />
      <path d="M10 3v10" />
    </>
  ),
  play: <path d="M5.5 3.75v8.5L12 8z" />,
  pause: <path d="M5.75 3.75v8.5M10.25 3.75v8.5" />,
  stop: <rect x="4.25" y="4.25" width="7.5" height="7.5" rx="1" />,
  plus: <path d="M8 3.5v9M3.5 8h9" />,
  check: <path d="M3.5 8.5l3 3 6-7" />,
  branch: (
    <>
      <circle cx="4.5" cy="3.75" r="1.5" />
      <circle cx="4.5" cy="12.25" r="1.5" />
      <circle cx="11.5" cy="5.25" r="1.5" />
      <path d="M4.5 5.25v5.5M11.5 6.75c0 2.75-3.5 2.25-7 4" />
    </>
  ),
  folder: <path d="M2 5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z" />,
  inbox: (
    <>
      <path d="M2.5 9.5l1.6-5.2a1 1 0 0 1 1-.8h5.8a1 1 0 0 1 1 .8l1.6 5.2v2.5a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1z" />
      <path d="M2.5 9.5h3l.8 1.5h3.4l.8-1.5h3" />
    </>
  ),
  user: (
    <>
      <circle cx="8" cy="5.5" r="2.5" />
      <path d="M3 13.25c.75-2.5 2.75-3.5 5-3.5s4.25 1 5 3.5" />
    </>
  ),
};

export const ICON_NAMES = Object.keys(PATHS);

/** A decorative icon. Unknown names render nothing. */
export function Icon({ name, className = "" }) {
  const shape = PATHS[name];
  if (!shape) return null;
  return (
    <svg
      className={["icon", className].filter(Boolean).join(" ")}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {shape}
    </svg>
  );
}
