import React from "react";

import { paths } from "../../app/paths";
import { Link } from "../../app/router";

import "../../styles/status.css";

export function NotFoundPage() {
  return (
    <section className="status-page" aria-labelledby="status-page-title">
      <h1 className="page-title" id="status-page-title">
        Nothing is at this address
      </h1>
      <p className="status-page__text">
        The link may be mistyped, or the page may have moved.{" "}
        <Link className="status-page__link" href={paths.workspace()}>
          Go to the workspace
        </Link>
      </p>
    </section>
  );
}
