import React, { useId } from "react";

/**
 * A labelled text input (or a textarea with `multiline`). The label is
 * always there for assistive technology; `hideLabel` hides it visually where
 * the context already says what the box is for. A `hint` and an `error` are
 * tied to the input with aria-describedby; an error marks it invalid.
 *
 * Every other prop goes to the input.
 */
export function Field({ label, hint, error, hideLabel = false, multiline = false, className = "", ...inputProps }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  const Input = multiline ? "textarea" : "input";
  return (
    <div className={["field", className].filter(Boolean).join(" ")}>
      <label className={hideLabel ? "visually-hidden" : "field__label"} htmlFor={id}>
        {label}
      </label>
      <Input
        id={id}
        className={multiline ? "field__input field__input--multiline" : "field__input"}
        type={multiline ? undefined : inputProps.type || "text"}
        aria-describedby={describedBy}
        aria-invalid={error ? "true" : undefined}
        {...inputProps}
      />
      {hint ? (
        <span className="field__hint" id={hintId}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span className="field__error" id={errorId}>
          {error}
        </span>
      ) : null}
    </div>
  );
}
