import React from "react";

/**
 * The small triangle on a control that opens more in place. It points
 * `right` on a closed line whose content opens under it, `down` where there
 * is more to show below, and `up` where what is shown can be folded again.
 * Sideways, on a board column: `left` folds it, `right` opens it again.
 * It takes the colour of the control's words.
 */
export function Caret({ direction = "down" }) {
  return <span className={`caret caret--${direction}`} aria-hidden="true" />;
}
