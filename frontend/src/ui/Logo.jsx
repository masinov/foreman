import React from "react";

/**
 * The wordmark. The F is drawn, not typed: a stem and two bars cut to the cap
 * height and weight of the letters beside it, with one gold square where the
 * short bar ends. The square is the task in hand; it breathes while
 * `running` (the engine of the project in view is working).
 */
export function Logo({ running = false }) {
  return (
    <span className={running ? "logo logo--running" : "logo"}>
      <svg className="logo__f" viewBox="0 0 7.5 10.9" aria-hidden="true" focusable="false">
        <path className="logo__letter" d="M0 0H7.5V1.77H1.77V4.8H4.05V6.57H1.77V10.9H0Z" />
        <rect className="logo__task" x="5.02" y="4.8" width="1.77" height="1.77" />
      </svg>
      <span className="logo__rest">oreman</span>
    </span>
  );
}
