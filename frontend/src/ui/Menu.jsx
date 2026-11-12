import React, { useEffect, useId, useRef, useState } from "react";

import { Link } from "../app/router";

/**
 * A menu behind a button. It opens on click and on Enter, Space or the
 * arrow keys; arrow keys, Home and End move between items; Escape and a
 * click outside close it; choosing an item or Escape returns focus to the
 * button.
 *
 * `label` names the menu; the button is named by `trigger` (its content) or
 * `triggerLabel`. Other props go to the button.
 *
 * `items` are `{ key, label, detail?, href?, onSelect?, current? }`. An item
 * with `href` is a link (it can open in a new tab); otherwise `onSelect`
 * runs. `current` marks the item the person is on.
 */
export function Menu({ label, trigger, triggerLabel, items, className = "", triggerClassName = "", ...triggerProps }) {
  const [open, setOpen] = useState(false);
  const [focusIndex, setFocusIndex] = useState(0);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const itemRefs = useRef([]);
  const menuId = useId();

  function openAt(index) {
    setFocusIndex(index);
    setOpen(true);
  }

  function startIndex() {
    const current = items.findIndex((item) => item.current);
    return current >= 0 ? current : 0;
  }

  function close({ refocus = true } = {}) {
    setOpen(false);
    if (refocus) triggerRef.current?.focus();
  }

  useEffect(() => {
    if (open) itemRefs.current[focusIndex]?.focus();
  }, [open, focusIndex]);

  useEffect(() => {
    if (!open) return undefined;
    function handlePointer(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handlePointer);
    return () => document.removeEventListener("mousedown", handlePointer);
  }, [open]);

  function handleTriggerKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      openAt(open ? focusIndex : startIndex());
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openAt(items.length - 1);
    }
  }

  function handleMenuKeyDown(event) {
    const last = items.length - 1;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setFocusIndex((index) => (index >= last ? 0 : index + 1));
        break;
      case "ArrowUp":
        event.preventDefault();
        setFocusIndex((index) => (index <= 0 ? last : index - 1));
        break;
      case "Home":
        event.preventDefault();
        setFocusIndex(0);
        break;
      case "End":
        event.preventDefault();
        setFocusIndex(last);
        break;
      case "Escape":
        event.preventDefault();
        close();
        break;
      case "Tab":
        setOpen(false);
        break;
      default:
    }
  }

  function choose(item) {
    item.onSelect?.();
    close();
  }

  return (
    <div className={["menu", className].filter(Boolean).join(" ")} ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={["menu__trigger", triggerClassName].filter(Boolean).join(" ")}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={triggerLabel}
        {...triggerProps}
        onClick={() => (open ? close({ refocus: false }) : openAt(startIndex()))}
        onKeyDown={handleTriggerKeyDown}
      >
        {trigger}
        <span className="menu__caret" aria-hidden="true" />
      </button>
      {open ? (
        <ul className="menu__list" role="menu" id={menuId} aria-label={label} onKeyDown={handleMenuKeyDown}>
          {items.map((item, index) => {
            const content = (
              <>
                <span className="menu__label">{item.label}</span>
                {item.detail !== undefined && item.detail !== null ? (
                  <span className="menu__detail">{item.detail}</span>
                ) : null}
              </>
            );
            const shared = {
              ref: (element) => {
                itemRefs.current[index] = element;
              },
              role: "menuitem",
              tabIndex: index === focusIndex ? 0 : -1,
              className: ["menu__item", item.current ? "menu__item--current" : ""].filter(Boolean).join(" "),
              "aria-current": item.current ? "page" : undefined,
              onMouseEnter: () => setFocusIndex(index),
            };
            return (
              <li key={item.key} role="none">
                {item.href ? (
                  <Link href={item.href} {...shared} onClick={() => close()}>
                    {content}
                  </Link>
                ) : (
                  <button
                    type="button"
                    {...shared}
                    onClick={() => choose(item)}
                  >
                    {content}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
