import React, { useId, useLayoutEffect, useRef, useState } from "react";

/**
 * Text as it was written, line breaks kept. Text longer than a dozen lines
 * is folded to that height with a "Show all" under it, so a long text does
 * not push the rest of the page out of reach. Short text gets no control.
 *
 * The control must not read as one more line of the text above it: it is
 * gold, in the size and weight of a control, with a caret that points down
 * while there is more to show and up once it is all shown.
 */
export function LongText({ children, className = "" }) {
  const ref = useRef(null);
  const id = useId();
  const [open, setOpen] = useState(false);
  const [folds, setFolds] = useState(false);

  // Whether it folds is a fact about the rendered text at this width: measure
  // it while folded, and again when the window changes size.
  useLayoutEffect(() => {
    if (open) return undefined;
    const measure = () => {
      const el = ref.current;
      if (el) setFolds(el.scrollHeight > el.clientHeight + 1);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [children, open]);

  return (
    <div className="long-text">
      <p
        ref={ref}
        id={id}
        className={["long-text__text", open ? "" : "long-text__text--folded", className].filter(Boolean).join(" ")}
      >
        {children}
      </p>
      {folds ? (
        <button
          type="button"
          className={open ? "long-text__toggle long-text__toggle--open" : "long-text__toggle"}
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen(!open)}
        >
          <span className="long-text__caret" aria-hidden="true" />
          {open ? "Show less" : "Show all"}
        </button>
      ) : null}
    </div>
  );
}
