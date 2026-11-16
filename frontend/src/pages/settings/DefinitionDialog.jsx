import React, { useEffect, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { resetDefinition, saveDefinition } from "../../api/definitions";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";
import { idFromName } from "./definitionWords";

/**
 * The frame both editors share: a form or the definition's text, saving,
 * the API's refusal, and going back to what Foreman ships.
 *
 * `definition` is the one being edited, or null for a new one, which starts
 * as a copy of `copyOf`. `fields()` answers the form's fields, or throws an
 * Error whose message says what is missing. `children` is the form.
 */
export function DefinitionDialog({
  open,
  kind,
  projectId,
  definition,
  copyOf,
  name,
  fields,
  onClose,
  onSaved,
  children,
  className = "dialog--wide",
}) {
  const client = useApiClient();
  const isNew = !definition;
  const [asText, setAsText] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setAsText(false);
    setText(definition?.text ?? "");
    setError(null);
  }, [open, definition?.id, definition?.text]);

  const id = isNew ? idFromName(name) : definition.id;

  async function act(request) {
    setBusy(true);
    setError(null);
    try {
      onSaved(await request());
    } catch (caught) {
      setError(errorSentence(caught));
    } finally {
      setBusy(false);
    }
  }

  function save(event) {
    event.preventDefault();
    if (asText) {
      act(() => saveDefinition(client, projectId, kind, id, { text }));
      return;
    }
    let body;
    try {
      body = { fields: fields() };
    } catch (caught) {
      setError(caught.message);
      return;
    }
    if (isNew) {
      if (!id) {
        setError(`A ${kind} needs a name that starts with a letter.`);
        return;
      }
      body.copy_of = copyOf;
    }
    act(() => saveDefinition(client, projectId, kind, id, body));
  }

  const origin = definition?.origin;
  const formId = `${kind}-editor`;
  return (
    <Dialog
      open={open}
      title={isNew ? `New ${kind}` : definition.name}
      onClose={onClose}
      className={className}
      footer={
        <>
          <span className="definition__left">
            {origin === "changed" ? (
              <Button
                variant="quiet"
                disabled={busy}
                onClick={() => act(() => resetDefinition(client, projectId, kind, definition.id))}
              >
                {projectId ? `Back to the default ${kind}` : `Back to the shipped ${kind}`}
              </Button>
            ) : null}
            {origin === "own" ? (
              <Button
                variant="quiet"
                disabled={busy}
                onClick={() => act(() => resetDefinition(client, projectId, kind, definition.id))}
              >
                Remove this {kind}
              </Button>
            ) : null}
            {isNew ? null : (
              <Button variant="quiet" onClick={() => setAsText(!asText)}>
                {asText ? "Edit as a form" : "Edit as text"}
              </Button>
            )}
          </span>
          <Button variant="quiet" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <form id={formId} className="dialog__body" onSubmit={save} noValidate>
        {asText ? (
          <Field
            label={`The ${kind} as TOML`}
            multiline
            className="definition__text"
            spellCheck={false}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        ) : (
          children
        )}
        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}
