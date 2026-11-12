import React from "react";

import { Button } from "../ui/Button";

/** The top bar's "Manager" toggle, on every page inside a project. */
export function ManagerToggle({ open, onToggle }) {
  return (
    <Button className="topbar__toggle" variant="quiet" inRow icon="panel" aria-pressed={open} onClick={onToggle}>
      Manager
    </Button>
  );
}
