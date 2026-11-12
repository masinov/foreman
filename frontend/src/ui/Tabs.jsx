import React from "react";

import { Link, useRoute } from "../app/router";
import { normalizePath } from "../app/paths";

/**
 * Text tabs with the gold underline under the current one. Each tab is a real
 * link, so a tab opens in a new browser tab and has an address.
 */
export function Tabs({ label, items }) {
  const { pathname } = useRoute();
  const current = normalizePath(pathname);
  return (
    <nav className="tabs" aria-label={label}>
      <ul className="tabs__list">
        {items.map((item) => {
          const selected = normalizePath(item.href) === current;
          return (
            <li key={item.href} className="tabs__item">
              <Link
                href={item.href}
                className={["tabs__link", selected ? "tabs__link--current" : ""].filter(Boolean).join(" ")}
                aria-current={selected ? "page" : undefined}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
