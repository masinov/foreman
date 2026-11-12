import React from "react";

const TONES = new Set(["running", "passed", "failed", "attention", "idle"]);

/**
 * Status is a 6px dot and a word, never a pill. The word carries the meaning;
 * the dot's colour repeats it.
 */
export function StatusDot({ tone = "idle", children, className = "" }) {
  const resolved = TONES.has(tone) ? tone : "idle";
  return (
    <span className={["status", `status--${resolved}`, className].filter(Boolean).join(" ")}>
      <span className="status__dot" aria-hidden="true" />
      <span className="status__word">{children}</span>
    </span>
  );
}
