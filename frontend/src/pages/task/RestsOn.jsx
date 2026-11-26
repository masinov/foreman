import React, { useState } from "react";

import { getTaskDocument } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { Dialog } from "../../ui/Dialog";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { shortCommit } from "../shared/restsOn";

/** A document as it was at the commit it was named at, in a dialog. */
function DocumentDialog({ task, document, onClose }) {
  const file = useResource(["task-document", task.id, document.path, document.commit], (client, options) =>
    getTaskDocument(client, task.id, document.path, options),
  );
  return (
    <Dialog open title={document.path} description={`As it was at ${shortCommit(document.commit)}.`} onClose={onClose}>
      <div className="dialog__body">
        {file.error ? (
          <p className="notice notice--error" role="alert">
            {file.error}
          </p>
        ) : null}
        {file.data?.truncated ? (
          <p className="notice" role="status">
            The first {file.data.cap_chars.toLocaleString("en-US")} of {file.data.total_chars.toLocaleString("en-US")} characters are shown.
          </p>
        ) : null}
        {file.data ? <pre className="rests-on__text">{file.data.text}</pre> : null}
      </div>
    </Dialog>
  );
}

/**
 * The documents the task rests on, each with the commit it was named at and
 * a link that opens the file as it was then. Nothing when none is named.
 */
export function RestsOn({ task }) {
  const [open, setOpen] = useState(null);
  const documents = task.rests_on ?? [];
  if (!documents.length) return null;
  return (
    <section className="task-section" aria-labelledby="task-rests-on">
      <SectionHeading id="task-rests-on" title="Rests on" />
      <ul className="task-details__list">
        {documents.map((item) => (
          <li key={`${item.path}#${item.heading}`}>
            <button type="button" className="row-link rests-on__open" onClick={() => setOpen(item)}>
              {item.path}
            </button>
            {item.heading ? <span className="secondary">, {item.heading}</span> : null}{" "}
            <span className="quiet">
              named at <Mono quiet>{shortCommit(item.commit)}</Mono>
            </span>
          </li>
        ))}
      </ul>
      {open ? <DocumentDialog task={task} document={open} onClose={() => setOpen(null)} /> : null}
    </section>
  );
}
