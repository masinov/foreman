import React from "react";

import "../../styles/status.css";

/**
 * The one page every route without a rebuilt page renders. It says so and
 * links to the same place in the pre-v7 dashboard. It does not imitate the
 * page that will be here.
 */
export function RebuildingPage({ route, params }) {
  const legacyHref = route.legacyHref(params);
  return (
    <section className="status-page" aria-labelledby="status-page-title">
      <h1 className="page-title" id="status-page-title">
        This page is being rebuilt
      </h1>
      <p className="status-page__text">
        {route.title} is part of the dashboard rebuild and is not here yet. Everything you can do
        today is in the previous dashboard.
      </p>
      <p className="status-page__text">
        {/* A plain anchor: the previous dashboard is a separate application. */}
        <a className="status-page__link" href={legacyHref}>
          {route.legacyExact ? "Open this in the previous dashboard" : "Open the previous dashboard"}
        </a>
        {route.legacyExact ? null : (
          <span className="status-page__note"> It has no address of its own for this page; find it from its project.</span>
        )}
      </p>
    </section>
  );
}
