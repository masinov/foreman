import React, { useId, useState } from "react";

/**
 * A closed line that opens in place. The summary is a button carrying
 * aria-expanded; the content is rendered only while open, so what it loads
 * is loaded only when someone asks for it.
 */
export function Disclosure({ summary, defaultOpen = false, onToggle, className = "", children }) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();

  function toggle() {
    const next = !open;
    setOpen(next);
    onToggle?.(next);
  }

  return (
    <div className={["disclosure", open ? "disclosure--open" : "", className].filter(Boolean).join(" ")}>
      <button
        type="button"
        className="disclosure__summary"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={toggle}
      >
        <span className="disclosure__marker" aria-hidden="true" />
        {summary}
      </button>
      <div className="disclosure__content" id={contentId} hidden={!open}>
        {open ? children : null}
      </div>
    </div>
  );
}
