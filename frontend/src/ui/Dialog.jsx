import React, { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { FOCUSABLE, wrapTab } from "./focus";

/**
 * A modal dialog. It is labelled by its title, keeps keyboard focus inside
 * itself while open (Tab and Shift+Tab wrap), closes on Escape, and gives
 * focus back to what had it when it opened.
 *
 * Focus starts on the first element marked `data-autofocus`, else on the
 * first focusable element. `footer` holds the actions.
 */
export function Dialog({ open, title, description, onClose, footer, children, className = "" }) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement;
    const panel = panelRef.current;
    const first = panel.querySelector("[data-autofocus]") || panel.querySelector(FOCUSABLE) || panel;
    first.focus();
    return () => {
      if (previous && typeof previous.focus === "function" && document.contains(previous)) previous.focus();
    };
  }, [open]);

  if (!open) return null;

  function handleKeyDown(event) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onCloseRef.current?.();
      return;
    }
    wrapTab(event, panelRef.current);
  }

  return createPortal(
    <div className="dialog-backdrop">
      <div
        ref={panelRef}
        className={["dialog", className].filter(Boolean).join(" ")}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <h2 className="dialog__title" id={titleId}>
          {title}
        </h2>
        {description ? (
          <p className="dialog__description" id={descriptionId}>
            {description}
          </p>
        ) : null}
        <div className="dialog__body">{children}</div>
        {footer ? <div className="dialog__footer">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
