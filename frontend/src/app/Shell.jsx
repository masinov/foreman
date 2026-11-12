import React from "react";

import { Breadcrumb } from "./Breadcrumb";
import { paths } from "./paths";
import { Logo } from "../ui/Logo";
import { Link } from "./router";
import { UserMenu } from "./UserMenu";

/**
 * The frame every page sits in: the top bar (the word, the breadcrumb, a
 * right-hand slot), the page container, and the manager side bar slot.
 *
 * The manager side bar takes its own column when `manager` is given and
 * `managerOpen`; it is outside the page, so it stays put as pages change.
 */
export function Shell({ topBarRight = null, manager = null, managerOpen = false, children }) {
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar__inner">
          <Link className="topbar__home" href={paths.workspace()} aria-label="Foreman" title="Workspace: all projects">
            <Logo />
          </Link>
          <Breadcrumb />
          <div className="topbar__right">
            {topBarRight}
            <UserMenu />
          </div>
        </div>
      </header>
      <div className="shell__body">
        <main className="page" id="main" tabIndex={-1}>
          {children}
        </main>
        {manager && managerOpen ? (
          <aside className="manager-slot" aria-label="Manager" data-open="true">
            {manager}
          </aside>
        ) : null}
      </div>
    </div>
  );
}
