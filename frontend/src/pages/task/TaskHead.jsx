import React, { useState } from "react";

import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { shortSha } from "../../ui/format";
import { EditTaskDialog } from "./EditTaskDialog";
import { TaskActions } from "./TaskActions";

/** The commit the task's branch is at: from its changes, else from its checks. */
export function headCommit(changes, checks) {
  return changes?.head?.sha || checks?.facts?.tests?.head_sha || null;
}

/** "+118 −7", or "" when nothing changed or the size is not known. */
export function changeSize(changes) {
  const totals = changes?.totals;
  if (!totals || totals.files === 0) return "";
  return `+${totals.added} −${totals.deleted}`;
}

/**
 * Title, the mono line (key, type, branch, commit, size of change), Edit and
 * More. The same on all four tabs. `onChanged(sentence)` runs after an edit
 * or an action; `onDeleted()` after the task is gone.
 */
export function TaskHead({ task, changes, checks, onChanged, onDeleted }) {
  const [editing, setEditing] = useState(false);
  const facts = [task.task_key, task.task_type, task.branch_name, shortSha(headCommit(changes, checks)), changeSize(changes)].filter(
    Boolean,
  );
  return (
    <div className="task__title-row">
      <div className="task__title">
        <h1 className="page-title">{task.title}</h1>
        {facts.length ? (
          <Mono quiet className="task__facts">
            {facts.join(" · ")}
          </Mono>
        ) : null}
      </div>
      <div className="task__actions">
        <Button onClick={() => setEditing(true)}>Edit</Button>
        <TaskActions task={task} onDone={(name, sentence) => (name === "delete" ? onDeleted() : onChanged(sentence))} />
      </div>
      <EditTaskDialog
        open={editing}
        task={task}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          onChanged("Saved.");
        }}
      />
    </div>
  );
}
