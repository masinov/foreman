import React from "react";

/** Keys, commits, paths and amounts: JetBrains Mono at the mono size. */
export function Mono({ quiet = false, className = "", children, ...rest }) {
  const classes = ["mono", quiet ? "mono--quiet" : "", className].filter(Boolean).join(" ");
  return (
    <span className={classes} {...rest}>
      {children}
    </span>
  );
}
