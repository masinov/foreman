import React from "react";

import { Breadcrumb } from "./Breadcrumb";
import { paths } from "./paths";
import { Link } from "./router";

/**
 * The frame every page sits in: the top bar (the word, the breadcrumb, a
 * right-hand slot), the page container, and the manager side bar slot.
 *
 * The manager side bar is a later slice. Its slot is here, empty and
 * closed, so pages do not have to change when it arrives.
 */
export function Shell({ topBarRight = null, children }) {
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar__inner">
          <Link className="topbar__word" href={paths.workspace()}>
            Foreman
          </Link>
          <span className="topbar__divider" aria-hidden="true">
            /
          </span>
          <Breadcrumb />
          <div className="topbar__right">{topBarRight}</div>
        </div>
      </header>
      <div className="shell__body">
        <main className="page" id="main" tabIndex={-1}>
          {children}
        </main>
        <aside className="manager-slot" aria-label="Manager" data-open="false" hidden />
      </div>
    </div>
  );
}
