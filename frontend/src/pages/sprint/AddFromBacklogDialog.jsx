import React, { useEffect, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { BACKLOG_STATES, listBacklog, planBacklog } from "../../api/backlog";
import { errorSentence } from "../../api/client";
import { usePagedList } from "../../api/usePagedList";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { plural } from "../../ui/format";

const PAGE = 25;

/**
 * Accepted backlog work to plan into this sprint (ADR-0021). Choosing tasks
 * and confirming calls the backlog's plan endpoint with this sprint; when the
 * API refuses, its sentence is shown and nothing is lost.
 */
export function AddFromBacklogDialog({ open, projectId, sprint, onClose, onPlanned }) {
  const client = useApiClient();
  const list = usePagedList(
    ["sprint-add-backlog", projectId],
    (apiClient, options) => listBacklog(apiClient, projectId, { statuses: [BACKLOG_STATES.accepted], ...options }),
    { pageSize: PAGE, enabled: open && Boolean(projectId) },
  );
  const [selected, setSelected] = useState(() => new Set());
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setSelected(new Set());
      setError(null);
    }
  }, [open]);

  const items = list.items ?? [];
  const chosen = items.filter((task) => selected.has(task.id));

  function toggle(task) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(task.id)) next.delete(task.id);
      else next.add(task.id);
      return next;
    });
  }

  async function submit(event) {
    event.preventDefault();
    if (chosen.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      await planBacklog(client, projectId, { taskIds: chosen.map((task) => task.id), sprintId: sprint.id });
      onPlanned(chosen.length);
    } catch (failure) {
      setError(errorSentence(failure));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      title="Add from backlog"
      description={`Accepted work waiting to be planned. Chosen tasks move into ${sprint.title}.`}
      onClose={onClose}
    >
      <form className="dialog__body" onSubmit={submit}>
        {list.error ? (
          <p className="notice notice--error" role="alert">
            {list.error}
          </p>
        ) : null}
        {list.items && items.length === 0 ? (
          <p className="empty">Nothing is waiting to be planned. Accepted work appears here until it is planned into a sprint.</p>
        ) : null}
        {items.length > 0 ? (
          <ul className="choice-list">
            {items.map((task) => (
              <li key={task.id} className="choice-list__item">
                <label className="choice-list__label">
                  <input
                    type="checkbox"
                    className="checkbox"
                    checked={selected.has(task.id)}
                    onChange={() => toggle(task)}
                  />
                  <span>{task.title}</span>
                  <span className="quiet">{task.task_type}</span>
                </label>
              </li>
            ))}
          </ul>
        ) : null}
        {list.hasMore ? (
          <Button variant="quiet" disabled={list.loadingMore} onClick={() => list.loadMore()}>
            Show more
          </Button>
        ) : null}
        {error ? (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="dialog__footer">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving || chosen.length === 0}>
            {saving ? "Planning…" : chosen.length ? `Plan ${plural(chosen.length, "task")}` : "Plan"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
