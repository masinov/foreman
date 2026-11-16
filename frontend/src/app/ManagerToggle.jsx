import React from "react";

import { Button } from "../ui/Button";

/**
 * The top bar's toggle for the side bar, on every page inside a project:
 * "Manager" on a project or a sprint, "Agent" on a task.
 */
export function ManagerToggle({ open, onToggle, word = "Manager" }) {
  return (
    <Button className="topbar__toggle" variant="quiet" inRow icon="panel" aria-pressed={open} onClick={onToggle}>
      <span className="topbar__word">{word}</span>
    </Button>
  );
}
