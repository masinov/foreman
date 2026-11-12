import React, { useState } from "react";

import { Button } from "../../ui/Button";

/**
 * Copy `text` to the clipboard. It says "Copied" when the browser accepted it
 * and, when it did not (no clipboard access on this address), says so and
 * leaves the text for the person to select.
 */
export function CopyButton({ text, label = "Copy" }) {
  const [state, setState] = useState("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  return (
    <span className="copy">
      <Button onClick={copy}>{state === "copied" ? "Copied" : label}</Button>
      <span className="copy__status" role="status">
        {state === "failed" ? "The browser would not copy. Select the text and copy it." : ""}
      </span>
    </span>
  );
}
