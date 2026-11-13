import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { deleteSprint, SPRINT_STATUSES, transitionSprint } from "../../api/sprints";
import { paths } from "../../app/paths";
import { useNavigate } from "../../app/router";
import { Button } from "../../ui/Button";
import { Menu } from "../../ui/Menu";
import { Mono } from "../../ui/Mono";
import { formatDay, formatMoney, formatTokens } from "../../ui/format";
import { TaskCounts } from "../shared/TaskCounts";
import { ReasonDialog } from "../shared/ReasonDialog";
import { EditSprintDialog } from "./EditSprintDialog";

// The one state change that applies to a sprint now.
const STATE_ACTIONS = {
  [SPRINT_STATUSES.planned]: { label: "Activate sprint", doing: "Activating…", target: SPRINT_STATUSES.active },
  [SPRINT_STATUSES.active]: { label: "Finish sprint", doing: "Finishing…", target: SPRINT_STATUSES.completed },
};

/**
 * What More offers, each with what will happen in words. Cancel exists while
 * a sprint is planned or active; delete always.
 */
export const SPRINT_ACTIONS = {
  cancel: {
    label: "Cancel sprint",
    title: "Cancel this sprint",
    effect:
      "The sprint is closed as cancelled and nothing in it runs again. Its tasks and their history stay. It cannot be reopened.",
    confirm: "Cancel sprint",
    doing: "Cancelling…",
    run: (client, sprint) => transitionSprint(client, sprint.id, SPRINT_STATUSES.cancelled),
  },
  delete: {
    label: "Delete sprint",
    title: "Delete this sprint",
    effect: "The sprint, its tasks, their runs and their history are deleted. This cannot be undone.",
    confirm: "Delete sprint",
    doing: "Deleting…",
    run: (client, sprint) => deleteSprint(client, sprint.id),
  },
};

export function sprintActionsFor(sprint) {
  const open = sprint.status === SPRINT_STATUSES.planned || sprint.status === SPRINT_STATUSES.active;
  return open ? ["cancel", "delete"] : ["delete"];
}

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
  const navigate = useNavigate();
  const [chosen, setChosen] = useState(null);
  const more = chosen ? SPRINT_ACTIONS[chosen] : null;

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
          <Menu
            label="Sprint actions"
            trigger="More"
            className="sprint__more"
            triggerClassName="menu__trigger--button"
            items={sprintActionsFor(sprint).map((name) => ({
              key: name,
              label: SPRINT_ACTIONS[name].label,
              onSelect: () => setChosen(name),
            }))}
          />
        </div>
      </div>
      <ReasonDialog
        open={Boolean(more)}
        title={more?.title}
        effect={more?.effect}
        confirm={more?.confirm}
        doing={more?.doing}
        run={() => more.run(client, sprint)}
        onClose={() => setChosen(null)}
        onDone={() => {
          const name = chosen;
          setChosen(null);
          // A deleted sprint has no page; go to the project it was in.
          if (name === "delete") navigate(paths.project(sprint.project_id));
          else onChanged();
        }}
      />
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
