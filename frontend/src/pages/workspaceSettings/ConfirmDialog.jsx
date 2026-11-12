import React, { useEffect, useState } from "react";

import { errorSentence } from "../../api/client";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";

/**
 * Ask before something that cannot be undone. `onConfirm` is async; a refusal
 * from the API is shown in the dialog and the dialog stays open.
 */
export function ConfirmDialog({ open, title, description, confirmLabel, busyLabel, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    setBusy(false);
    setError(null);
  }, [open]);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (caught) {
      setError(errorSentence(caught));
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      title={title}
      description={description}
      onClose={onClose}
      footer={
        <>
          <Button variant="quiet" onClick={onClose} data-autofocus>
            Cancel
          </Button>
          <Button disabled={busy} onClick={confirm}>
            {busy ? busyLabel : confirmLabel}
          </Button>
        </>
      }
    >
      {error ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}
    </Dialog>
  );
}
