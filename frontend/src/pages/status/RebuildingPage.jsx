import React from "react";

import { Mono } from "../../ui/Mono";

import "../../styles/status.css";

/**
 * The one page every route without a rebuilt page renders. It says the page
 * is not built yet and, where the route names one, the commands that do the
 * same job in a terminal. It links nowhere and does not imitate the page that
 * will be here.
 */
export function RebuildingPage({ route, params }) {
  const commands = route.cli ? route.cli(params) : [];
  return (
    <section className="status-page" aria-labelledby="status-page-title">
      <h1 className="page-title" id="status-page-title">
        This page is not built yet
      </h1>
      <p className="status-page__text">
        {route.title} is part of the dashboard rebuild and is not here yet.
        {commands.length > 0 ? " In a terminal, the same job is done with:" : ""}
      </p>
      {commands.length > 0 ? (
        <ul className="status-page__commands" aria-label="Commands">
          {commands.map((command) => (
            <li key={command}>
              <Mono>{command}</Mono>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
