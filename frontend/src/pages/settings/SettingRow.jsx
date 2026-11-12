import React, { useId } from "react";

import { SectionHeading } from "../../ui/SectionHeading";

/**
 * One row of a settings section: what it is called at the left, the control
 * and its hint at the right, and the API's refusal beside the control it is
 * about. `children(controlProps)` renders the control; the props tie it to the
 * label, the hint and the error. `group` is for a row whose control is not one
 * input (the label is then plain text).
 */
export function SettingRow({ label, hint, error, group = false, children }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="setting-row">
      <dt className="setting-row__label">{group ? label : <label htmlFor={id}>{label}</label>}</dt>
      <dd className="setting-row__value">
        <div className="setting-row__control">
          {children({ id, "aria-describedby": describedBy, "aria-invalid": error ? "true" : undefined })}
          {hint ? (
            <span className="setting-row__hint" id={hintId}>
              {hint}
            </span>
          ) : null}
        </div>
        {error ? (
          <p className="setting-row__error" id={errorId} role="alert">
            {error}
          </p>
        ) : null}
      </dd>
    </div>
  );
}

/** A row that cannot be changed here: the value, as text. */
export function ReadOnlyRow({ label, children, hint }) {
  return (
    <div className="setting-row">
      <dt className="setting-row__label">{label}</dt>
      <dd className="setting-row__value">
        <div className="setting-row__control">
          {children}
          {hint ? <span className="setting-row__hint">{hint}</span> : null}
        </div>
      </dd>
    </div>
  );
}

/** A titled group of rows. */
export function SettingsSection({ id, title, note, children }) {
  return (
    <section className="settings-section" aria-labelledby={id}>
      <SectionHeading id={id} title={title} note={note} />
      <dl className="settings-section__rows">{children}</dl>
    </section>
  );
}
