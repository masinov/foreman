import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "./Icon";

/** How long a confirmation stays before it goes (owner, 2026-11-24: about 6 seconds). */
export const TOAST_MS = 6000;

const ToastContext = createContext(null);

/**
 * The one place a success sentence is shown after an action: a passing note
 * in the same corner of the window on every page. It never moves the
 * page's content, a new one replaces the one showing, and it stays while the
 * pointer or focus is on it. Errors are not shown here: they ask the user to
 * act, so they stay inline where the action failed.
 *
 * The region is a live region and is always in the page, so a screen reader
 * announces the sentence when it appears.
 */
export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const [held, setHeld] = useState(false);
  const counter = useRef(0);

  const show = useCallback((text) => {
    const said = String(text ?? "").trim();
    if (!said) return;
    counter.current += 1;
    setToast({ id: counter.current, text: said });
  }, []);
  const dismiss = useCallback(() => setToast(null), []);

  // The time starts again for each sentence, and while it is held.
  const id = toast?.id;
  useEffect(() => {
    if (id === undefined || held) return undefined;
    const timer = setTimeout(() => setToast(null), TOAST_MS);
    return () => clearTimeout(timer);
  }, [id, held]);
  useEffect(() => {
    if (!toast) setHeld(false);
  }, [toast]);

  const value = useMemo(() => ({ show, dismiss }), [show, dismiss]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" role="status">
        {toast ? (
          <div
            className="toast"
            key={toast.id}
            onMouseEnter={() => setHeld(true)}
            onMouseLeave={() => setHeld(false)}
            onFocus={() => setHeld(true)}
            onBlur={() => setHeld(false)}
          >
            <span className="toast__text">{toast.text}</span>
            <button type="button" className="toast__close" aria-label="Dismiss" onClick={dismiss}>
              <Icon name="close" />
            </button>
          </div>
        ) : null}
      </div>
    </ToastContext.Provider>
  );
}

/** `show(sentence)` puts a success sentence in the toast; `dismiss()` removes it. */
export function useToast() {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast needs a ToastProvider above it.");
  return value;
}

/**
 * The notice state of an action: `[notice, setNotice]`. A success
 * (`{ error: false, text }`) is said in the toast; an error stays as the
 * returned `notice`, for the page to show inline where the action failed.
 * `setNotice(null)` clears the error.
 */
export function useNotice() {
  const { show } = useToast();
  const [error, setError] = useState(null);
  const setNotice = useCallback(
    (notice) => {
      if (notice && !notice.error) {
        setError(null);
        show(notice.text);
        return;
      }
      setError(notice);
    },
    [show],
  );
  return [error, setNotice];
}
