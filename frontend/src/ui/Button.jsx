import React from "react";
import { Icon } from "./Icon";

const VARIANTS = new Set(["default", "quiet", "gold-outline", "gold"]);

/**
 * A control button. Variants from the design README: `default`, `quiet`,
 * `gold-outline` (an approval in a list) and `gold` (the one decision on the
 * task page). `inRow` makes it the 24px control used inside table rows. `icon`
 * names an icon drawn before the label.
 */
export function Button({
  variant = "default",
  inRow = false,
  type = "button",
  icon = null,
  className = "",
  children,
  ...rest
}) {
  const resolved = VARIANTS.has(variant) ? variant : "default";
  const classes = ["button", `button--${resolved}`, inRow ? "button--in-row" : "", className]
    .filter(Boolean)
    .join(" ");
  return (
    <button type={type} className={classes} {...rest}>
      {icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
}
