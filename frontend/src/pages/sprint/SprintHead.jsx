import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { deleteSprint, SPRINT_STATUSES, transitionSprint } from "../../api/sprints";
import { askManager, planSprintRequest } from "../../app/managerRequests";
import { paths } from "../../app/paths";
import { useNavigate } from "../../app/router";
import { Button } from "../../ui/Button";
import { Menu } from "../../ui/Menu";
import { LongText } from "../../ui/LongText";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { formatDay, formatMoney, formatTokens, shortSha } from "../../ui/format";
import { TaskCounts } from "../shared/TaskCounts";
import { ReasonDialog } from "../shared/ReasonDialog";
import { EditSprintDialog } from "./EditSprintDialog";

// The one state change that applies to a sprint now.
const STATE_ACTIONS = {
  [SPRINT_STATUSES.planned]: { label: "Activate sprint", doing: "Activating…", target: SPRINT_STATUSES.active },
  [SPRINT_STATUSES.active]: { label: "Finish sprint", doing: "Finishing…", target: SPRINT_STATUSES.completed },
  [SPRINT_STATUSES.completed]: { label: "Reopen sprint", doing: "Reopening…", target: SPRINT_STATUSES.active },
};

/**
 * What More offers, each with what will happen in words. Cancel exists while
 * a sprint is planned or active; delete always.
 */
export const SPRINT_ACTIONS = {
  plan: {
    label: "Plan this sprint",
    title: "Plan this sprint",
    effect:
      "The manager reads the sprint's goal, the spec and the repository, and proposes the tasks that reach the goal. The proposal appears in the manager's side bar. Who confirms it is this project's \u201cApprove plans\u201d setting.",
    confirm: "Ask the manager",
    doing: "Asking…",
    run: async (client, sprint) => askManager(planSprintRequest(sprint)),
  },
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
  if (!open) return ["delete"];
  // Planning starts from the goal: a sprint without one has nothing to plan from.
  return (sprint.goal || "").trim() ? ["plan", "cancel", "delete"] : ["cancel", "delete"];
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
 * A finished sprint's checkpoint (spec 6.4): the tag on the default branch
 * and the commit it marks, the note when one was written, or why there is
 * no tag.
 */
function checkpointRows(checkpoint) {
  if (!checkpoint) return [];
  if (checkpoint.problem) {
    return [{ key: "tag", term: "Tag", value: <span className="tone-failed">Not tagged: {checkpoint.problem}</span> }];
  }
  return [
    {
      key: "tag",
      term: "Tag",
      value: (
        <span className="details-list__line">
          <Mono className="details-list__cut" title={checkpoint.tag}>
            {checkpoint.tag}
          </Mono>{" "}
          <span className="quiet">at {shortSha(checkpoint.sha)}</span>
        </span>
      ),
    },
    checkpoint.note_path
      ? {
          key: "note",
          term: "Note",
          value: (
            <span className="details-list__line">
              <Mono className="details-list__cut" title={checkpoint.note_path}>
                {checkpoint.note_path}
              </Mono>
            </span>
          ),
        }
      : null,
  ];
}

/**
 * The title row (Edit, the state action that applies, More), then the goal
 * beside the sprint's details, as a task's Overview sets what it is beside
 * its facts. `onChanged` runs after a save or a state change so the page
 * reads again.
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
  const details = [
    { key: "state", term: "State", value: stateSentence(sprint) },
    { key: "tasks", term: "Tasks", value: <TaskCounts counts={sprint.task_counts} /> },
    {
      key: "spend",
      term: "Spend",
      value: (
        <Mono>
          {formatMoney(totals.total_cost_usd)} · {formatTokens(totals.total_token_count)} tokens
        </Mono>
      ),
    },
    sprint.picks_own_tasks
      ? { key: "foreman", term: "Started by Foreman", value: `${sprint.started_by_foreman ?? 0} of ${sprint.foreman_limit ?? 0}` }
      : null,
    ...checkpointRows(sprint.checkpoint),
  ].filter(Boolean);
  return (
    <>
      <div className="sprint__title-row">
        <h1 className="page-title sprint__title">{sprint.title}</h1>
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
      <div className="page-overview">
        <section className="page-overview__main page-section" aria-labelledby="sprint-goal">
          <SectionHeading id="sprint-goal" title="Goal" />
          {sprint.goal ? (
            <LongText className="sprint__goal" short>
              {sprint.goal}
            </LongText>
          ) : (
            <p className="empty">No goal is written. Edit adds one; the manager plans the sprint from it.</p>
          )}
        </section>
        <section className="page-overview__aside page-section" aria-labelledby="sprint-details">
          <SectionHeading id="sprint-details" title="Details" />
          <dl className="details-list">
            {details.map((row) => (
              <div key={row.key} className="details-list__row">
                <dt>{row.term}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
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
