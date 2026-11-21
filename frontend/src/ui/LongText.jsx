import React, { useId, useLayoutEffect, useRef, useState } from "react";

import { Caret } from "./Caret";

/**
 * Text as it was written, line breaks kept. Text longer than a dozen lines
 * (four with `short`, where a page wants less of it at first) is folded to that
 * height with a "Show all" under it, so a long text does not push the rest
 * of the page out of reach. Short text gets no control.
 *
 * With `brief` it folds to its first three lines (a command an agent ran).
 * With `output` it is what a program printed (a tool's result, test output,
 * an error): monospace, quieter, and folded to its first three lines, with
 * the same "Show all" when there is more.
 *
 * The control must not read as one more line of the text above it: it has
 * the look of everything that opens more in place (`expander` in ui.css),
 * with a caret that points down while there is more to show and up once it
 * is all shown.
 */
export function LongText({ children, className = "", short = false, brief = false, output = false }) {
  const Tag = output ? "pre" : "p";
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
  }, [children, open, short, brief, output]);

  return (
    <div className="long-text">
      <Tag
        ref={ref}
        id={id}
        className={[
          "long-text__text",
          output ? "long-text__text--output" : "",
          open ? "" : "long-text__text--folded",
          short ? "long-text__text--short" : "",
          brief ? "long-text__text--brief" : "",
          className,
        ].filter(Boolean).join(" ")}
      >
        {children}
      </Tag>
      {folds ? (
        <button
          type="button"
          className="long-text__toggle expander"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen(!open)}
        >
          <Caret direction={open ? "up" : "down"} />
          {open ? "Show less" : "Show all"}
        </button>
      ) : null}
    </div>
  );
}
