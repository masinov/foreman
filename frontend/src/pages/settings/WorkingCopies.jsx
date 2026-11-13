import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { listWorkingCopies, removeUnusedWorkingCopies } from "../../api/projects";
import { useResource } from "../../api/useResource";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";
import { humanize, plural } from "../../ui/format";

// A task that is finished one way or another no longer needs its copy.
const FINISHED = new Set(["done", "cancelled", "declined"]);

function whose(copy) {
  if (copy.is_integration) return <span className="secondary">Where merges land</span>;
  if (!copy.task_id) return <span className="quiet">A task that no longer exists</span>;
  return (
    <Link className="row-link" href={paths.task(copy.task_id)}>
      <Mono>{copy.task_key || copy.slug}</Mono>
    </Link>
  );
}

function state(copy) {
  if (copy.is_integration) return <span className="quiet">Always kept</span>;
  if (!copy.exists) return <span className="quiet">Folder is gone</span>;
  if (!copy.task_id || FINISHED.has(copy.task_status)) return <span className="tone-attention">Unused</span>;
  return `In use, task ${humanize(copy.task_status).toLowerCase()}`;
}

const COLUMNS = [
  { key: "whose", header: "For", render: whose },
  { key: "branch", header: "Branch", render: (copy) => (copy.branch ? <Mono quiet>{copy.branch}</Mono> : null) },
  { key: "state", header: "State", render: state },
];

/**
 * The project's working copies on this machine: how many there are against
 * the limit, what each is for, and a way to remove the ones nothing uses.
 * Removing never touches the copy merges land in or a live task's copy.
 */
export function WorkingCopies({ projectId }) {
  const client = useApiClient();
  const list = useResource(["working-copies", projectId], (apiClient, options) =>
    listWorkingCopies(apiClient, projectId, options),
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  async function removeUnused() {
    setBusy(true);
    setNotice(null);
    try {
      const result = await removeUnusedWorkingCopies(client, projectId);
      const removed = result?.removed?.length ?? 0;
      setNotice({
        error: false,
        text: removed ? `Removed ${plural(removed, "working copy", "working copies")}.` : "Nothing to remove: every working copy is in use.",
      });
      list.reload();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setBusy(false);
    }
  }

  const data = list.data;
  const forTasks = data ? data.copies.filter((copy) => !copy.is_integration).length : null;
  return (
    <section className="settings-section" aria-labelledby="settings-copies">
      <SectionHeading
        id="settings-copies"
        title="Working copies"
        count={forTasks ?? undefined}
        note={
          data
            ? data.limit > 0
              ? `for tasks, of at most ${data.limit} at once. Each task is worked on in its own copy of the repository.`
              : "for tasks. Each task is worked on in its own copy of the repository."
            : null
        }
        actions={
          <Button disabled={busy || !data} onClick={removeUnused}>
            {busy ? "Removing…" : "Remove unused"}
          </Button>
        }
      />
      {list.error ? (
        <p className="notice notice--error" role="alert">
          {list.error}
        </p>
      ) : null}
      {notice ? (
        <p className={notice.error ? "notice notice--error" : "notice"} role={notice.error ? "alert" : "status"}>
          {notice.text}
        </p>
      ) : null}
      {data && data.copies.length > 0 ? (
        <Table caption="Working copies" columns={COLUMNS} rows={data.copies} rowKey={(copy) => copy.slug} />
      ) : null}
      {data && data.copies.length === 0 ? (
        <p className="empty">None yet. The first one is made when a task starts.</p>
      ) : null}
    </section>
  );
}
