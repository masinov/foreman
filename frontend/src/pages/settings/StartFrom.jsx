import React, { useEffect, useId, useState } from "react";

import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";

/** What a new definition is a copy of when it starts empty (the server's word). */
export const BLANK = "_blank";

/**
 * What a new role or workflow starts from: empty, or a copy of one there is.
 * `kind` is "role" or "workflow"; `items` are the ones to copy.
 */
export function StartFrom({ open, kind, items, onClose, onChosen }) {
  const id = useId();
  const [chosen, setChosen] = useState(BLANK);
  useEffect(() => {
    if (open) setChosen(BLANK);
  }, [open]);
  return (
    <Dialog
      open={open}
      title={`New ${kind}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => onChosen(chosen)}>Continue</Button>
        </>
      }
    >
      <div className="field">
        <label className="field__label" htmlFor={id}>
          Start from
        </label>
        <select id={id} className="field__input" value={chosen} data-autofocus onChange={(event) => setChosen(event.target.value)}>
          <option value={BLANK}>{kind === "role" ? "An empty role" : "An empty workflow"}</option>
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              A copy of {item.name}
            </option>
          ))}
        </select>
      </div>
    </Dialog>
  );
}
