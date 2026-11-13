import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { SPRINT_STATUSES, transitionSprint } from "../../api/sprints";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { formatDay, formatMoney, formatTokens } from "../../ui/format";
import { TaskCounts } from "../shared/TaskCounts";
import { EditSprintDialog } from "./EditSprintDialog";

// The one state change that applies to a sprint now.
const STATE_ACTIONS = {
  [SPRINT_STATUSES.planned]: { label: "Activate sprint", doing: "Activating…", target: SPRINT_STATUSES.active },
  [SPRINT_STATUSES.active]: { label: "Finish sprint", doing: "Finishing…", target: SPRINT_STATUSES.completed },
};

function stateSentence(sprint) {
  const started = formatDay(sprint.started_at);
  const finished = formatDay(sprint.completed_at);
  switch (sprint.status) {
    case SPRINT_STATUSES.active:
      return started ? `Active since ${started}` : "Active";
    case SPRINT_STATUSES.planned:
      return "Planned, not started";
    case SPRINT_STATUSES.completed:
      return finished ? `Finished ${finished}` : "Finished";
    case "cancelled":
      return "Cancelled";
    default:
      return sprint.status;
  }
}

/**
 * Title and goal, Edit, the state action that applies, and the summary row.
 * `onChanged` runs after a save or a state change so the page reads again.
 */
export function SprintHead({ sprint, onChanged }) {
  const client = useApiClient();
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [refusal, setRefusal] = useState(null);
  const action = STATE_ACTIONS[sprint.status] ?? null;

  async function changeState() {
    setPending(true);
    setRefusal(null);
    try {
      await transitionSprint(client, sprint.id, action.target);
      onChanged();
    } catch (error) {
      setRefusal(errorSentence(error));
    } finally {
      setPending(false);
    }
  }

  const totals = sprint.totals ?? {};
  return (
    <>
      <div className="sprint__title-row">
        <div className="sprint__title">
          <h1 className="page-title">{sprint.title}</h1>
          {sprint.goal ? <p className="sprint__goal">{sprint.goal}</p> : null}
        </div>
        <div className="sprint__actions">
          <Button onClick={() => setEditing(true)}>Edit</Button>
          {action ? (
            <Button disabled={pending} onClick={changeState}>
              {pending ? action.doing : action.label}
            </Button>
          ) : null}
        </div>
      </div>
      {refusal ? (
        <p className="notice notice--error" role="alert">
          {refusal}
        </p>
      ) : null}
      <dl className="summary">
        <div className="summary__item">
          <dt>State</dt>
          <dd>{stateSentence(sprint)}</dd>
        </div>
        <div className="summary__item">
          <dt>Tasks</dt>
          <dd>
            <TaskCounts counts={sprint.task_counts} />
          </dd>
        </div>
        <div className="summary__item">
          <dt>Spend</dt>
          <dd>
            <Mono>
              {formatMoney(totals.total_cost_usd)} · {formatTokens(totals.total_token_count)} tokens
            </Mono>
          </dd>
        </div>
        <div className="summary__item">
          <dt>Foreman picks its own tasks</dt>
          <dd>{sprint.picks_own_tasks ? "On" : "Off"}</dd>
        </div>
      </dl>
      <EditSprintDialog
        open={editing}
        sprint={sprint}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          onChanged();
        }}
      />
    </>
  );
}
