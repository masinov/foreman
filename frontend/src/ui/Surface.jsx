import React from "react";

/**
 * The one tinted surface. It means "act here": Needs you, and the decision on
 * the task page. Nothing else is boxed.
 */
export function Surface({ as: Element = "div", className = "", children, ...rest }) {
  return (
    <Element className={["surface", className].filter(Boolean).join(" ")} {...rest}>
      {children}
    </Element>
  );
}
