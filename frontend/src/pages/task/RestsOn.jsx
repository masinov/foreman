import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { getTaskDocument, getTaskDocumentChange, restampTaskDocument } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { Dialog } from "../../ui/Dialog";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { shortCommit } from "../shared/restsOn";
import { DiffLines } from "./ChangesTab";
import { parseDiff } from "./diff";

/** A document as it was at the commit it was named at, in a dialog. */
function DocumentDialog({ task, document, onClose }) {
  const file = useResource(["task-document", task.id, document.path, document.heading, document.commit], (client, options) =>
    getTaskDocument(client, task.id, document, options),
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

/** What changed in a document since the task named it: the diff between the two commits. */
function ChangeDialog({ task, document, onClose }) {
  const change = useResource(
    ["task-document-change", task.id, document.path, document.heading, document.commit, document.changed.commit],
    (client, options) => getTaskDocumentChange(client, task.id, document, options),
  );
  const rows = change.data ? parseDiff(change.data.diff) : [];
  return (
    <Dialog
      open
      title={`${document.path} changed`}
      description={`From ${shortCommit(document.commit)}, where this task named it, to ${shortCommit(document.changed.commit)}.`}
      onClose={onClose}
    >
      <div className="dialog__body">
        {change.error ? (
          <p className="notice notice--error" role="alert">
            {change.error}
          </p>
        ) : null}
        {change.data?.truncated ? (
          <p className="notice" role="status">
            The first {change.data.cap_chars.toLocaleString("en-US")} of {change.data.total_chars.toLocaleString("en-US")} characters are shown.
          </p>
        ) : null}
        {change.data ? <DiffLines rows={rows} /> : null}
      </div>
    </Dialog>
  );
}

/**
 * The documents the task rests on, each with the commit it was named at and
 * a link that opens the file as it was then. Nothing when none is named.
 * A document a merge changed since says so, opens the change, and can be
 * marked as read at the default branch's commit now, which ends the notice.
 */
export function RestsOn({ task, onChanged }) {
  const client = useApiClient();
  const [open, setOpen] = useState(null);
  const [diff, setDiff] = useState(null);
  const [marking, setMarking] = useState(null);
  const [error, setError] = useState(null);
  const documents = task.rests_on ?? [];
  if (!documents.length) return null;

  async function markRead(item) {
    const key = `${item.path}#${item.heading}`;
    setMarking(key);
    setError(null);
    try {
      const updated = await restampTaskDocument(client, task.id, item);
      const entry = (updated?.rests_on ?? []).find((other) => other.path === item.path && other.heading === item.heading);
      onChanged?.(`Marked ${item.path} as read at ${shortCommit(entry?.commit ?? item.changed.default_commit)}.`);
    } catch (failure) {
      setError(errorSentence(failure));
    } finally {
      setMarking(null);
    }
  }

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
            {item.changed ? (
              <>
                {" "}
                <span className="tone-attention">
                  changed in {item.changed.task_key ? `${item.changed.task_key}'s` : "a"} merge (<Mono quiet>{shortCommit(item.changed.commit)}</Mono>)
                  since it was named
                </span>{" "}
                <button type="button" className="row-link rests-on__diff" onClick={() => setDiff(item)}>
                  See what changed
                </button>{" "}
                <button
                  type="button"
                  className="row-link rests-on__read"
                  disabled={marking === `${item.path}#${item.heading}`}
                  onClick={() => markRead(item)}
                >
                  {item.changed.default_commit ? `Mark as read at ${shortCommit(item.changed.default_commit)}` : "Mark as read"}
                </button>
              </>
            ) : null}
          </li>
        ))}
      </ul>
      {error ? (
        <p className="notice notice--error" role="alert">
          {error}
        </p>
      ) : null}
      {diff ? <ChangeDialog task={task} document={diff} onClose={() => setDiff(null)} /> : null}
      {open ? <DocumentDialog task={task} document={open} onClose={() => setOpen(null)} /> : null}
    </section>
  );
}
