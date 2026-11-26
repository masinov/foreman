import React, { useState } from "react";

import { StatusDot } from "../../ui/StatusDot";
import { workWords } from "./workWords";

/**
 * A sprint's status line (ADR-0043 §6): a dot and one short line with no name
 * in it. Who, why and when are its detail: on hover, and on a tap, which is
 * how a phone reaches them.
 */
export function WorkStatus({ work, className = "" }) {
  const { tone, text, detail } = workWords(work);
  const [open, setOpen] = useState(false);
  const dot = <StatusDot tone={tone}>{text}</StatusDot>;
  return (
    <span className={["work-status", className].filter(Boolean).join(" ")}>
      {detail ? (
        <button
          type="button"
          className="work-status__toggle"
          title={detail}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {dot}
        </button>
      ) : (
        dot
      )}
      {open && detail ? <span className="work-status__detail">{detail}</span> : null}
    </span>
  );
}
