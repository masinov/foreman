import React from "react";

import { Link, useRoute } from "../app/router";
import { normalizePath } from "../app/paths";

/**
 * Text tabs with the gold underline under the current one. Each tab is a real
 * link, so a tab opens in a new browser tab and has an address.
 *
 * An item is `{ href, label, count?, current? }`: `count` is a figure beside
 * the label; `current` says the tab is the current one where more than one
 * address shows it (a sprint's Tasks as a list or a board). `controls` are
 * the current tab's own controls, on the tab line at its right, so they
 * leave no row of their own under it.
 */
export function Tabs({ label, items, controls = null }) {
  const { pathname } = useRoute();
  const current = normalizePath(pathname);
  return (
    <div className={controls ? "tabs tabs--with-controls" : "tabs"}>
      <nav className="tabs__nav" aria-label={label}>
        <ul className="tabs__list">
          {items.map((item) => {
            const selected = item.current ?? normalizePath(item.href) === current;
            return (
              <li key={item.href} className="tabs__item">
                <Link
                  href={item.href}
                  className={["tabs__link", selected ? "tabs__link--current" : ""].filter(Boolean).join(" ")}
                  aria-current={selected ? "page" : undefined}
                >
                  {item.label}
                  {item.count !== undefined && item.count !== null ? (
                    <>
                      <span className="visually-hidden"> </span>
                      <span className="tabs__count">{item.count}</span>
                    </>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {controls ? <div className="tabs__controls">{controls}</div> : null}
    </div>
  );
}
