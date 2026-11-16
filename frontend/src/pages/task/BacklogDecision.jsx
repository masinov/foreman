import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { acceptTask, declineTask, planBacklog } from "../../api/backlog";
import { errorSentence } from "../../api/client";
import { listProjectSprints, SPRINT_STATUSES } from "../../api/sprints";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Surface } from "../../ui/Surface";
import { formatDay } from "../../ui/format";
import { PlanNewSprintDialog } from "../project/PlanNewSprintDialog";
import { ReasonDialog } from "../shared/ReasonDialog";
import { filedBy } from "./taskWords";

const NEW_SPRINT = "new";

/**
 * What to do with a task that is in the backlog, on the tinted surface where
 * a task's decision goes: plan it into a sprint, or decline it.
 *
 * A request (work an agent or another system filed that no person has
 * accepted) can also be accepted, where the project lets Foreman start
 * backlog work on its own: that is what accepting allows (ADR-0028).
 * Planning a request is accepting it. `onDecided(sentence)` runs once the
 * API took the decision.
 */
export function BacklogDecision({ task, onDecided }) {
  const client = useApiClient();
  const sprints = useResource(["backlog-sprints", task.project_id], (apiClient, options) =>
    listProjectSprints(apiClient, task.project_id, {
      statuses: [SPRINT_STATUSES.active, SPRINT_STATUSES.planned],
      order: "queue",
      ...options,
    }),
  );
  const targets = sprints.data?.items ?? [];
  const [picked, setPicked] = useState(null);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState(null);
  const [naming, setNaming] = useState(false);
  const [declining, setDeclining] = useState(false);
  // The first sprint in the queue until another is chosen; a new one if there is none.
  const target = picked ?? targets[0]?.id ?? NEW_SPRINT;
  const request = task.status === "triage";
  const mayAccept = request && task.foreman_starts_backlog_work;
  const who = filedBy(task);
  const when = formatDay(task.created_at);

  async function act(run, sentence) {
    setBusy(true);
    setRefusal(null);
    try {
      await run();
      onDecided(sentence);
      return null;
    } catch (error) {
      const text = errorSentence(error);
      setRefusal(text);
      return text;
    } finally {
      setBusy(false);
    }
  }

  function plan() {
    if (target === NEW_SPRINT) {
      setNaming(true);
      return;
    }
    const sprint = targets.find((entry) => entry.id === target);
    act(
      () => planBacklog(client, task.project_id, { taskIds: [task.id], sprintId: target }),
      `Planned into ${sprint?.title ?? "the sprint"}.`,
    );
  }

  return (
    <Surface as="section" className="decision" aria-labelledby="task-decision">
      <div className="decision__body">
        <h2 className="decision__question" id="task-decision">
          {request ? "A request: plan it into a sprint?" : "Plan this into a sprint?"}
        </h2>
        <ul className="decision__facts">
          {who ? (
            <li>
              Filed by {who}
              {when ? ` on ${when}` : ""}
            </li>
          ) : null}
          {task.source?.url ? (
            <li>
              <a href={task.source.url} target="_blank" rel="noreferrer">
                {task.source.external_ref || "Where it was filed"}
              </a>
            </li>
          ) : null}
          <li>Type: {task.task_type}</li>
        </ul>
        {refusal ? (
          <p className="notice notice--error" role="alert">
            {refusal}
          </p>
        ) : null}
      </div>
      <div className="decision__actions">
        <Button disabled={busy} onClick={() => setDeclining(true)}>
          Decline
        </Button>
        {mayAccept ? (
          <Button
            variant="gold-outline"
            disabled={busy}
            aria-label="Accept: Foreman may start it"
            onClick={() => act(() => acceptTask(client, task.id), "Accepted. Foreman may start it.")}
          >
            Accept
          </Button>
        ) : null}
        <select
          className="field__input decision__sprint"
          aria-label="Sprint to plan it into"
          value={target}
          onChange={(event) => setPicked(event.target.value)}
        >
          {targets.map((sprint) => (
            <option key={sprint.id} value={sprint.id}>
              {sprint.title} ({sprint.status})
            </option>
          ))}
          <option value={NEW_SPRINT}>A new sprint</option>
        </select>
        <Button variant="gold" disabled={busy} onClick={plan}>
          Plan
        </Button>
      </div>
      <ReasonDialog
        open={declining}
        title="Decline this task"
        effect="The task stays in the backlog, marked declined. Nothing runs it."
        ask="Why it is declined"
        hint="Optional. Kept with the task in the backlog."
        required={false}
        confirm="Decline"
        doing="Recording…"
        run={(text) => declineTask(client, task.id, { reason: text })}
        onClose={() => setDeclining(false)}
        onDone={() => {
          setDeclining(false);
          onDecided("Declined.");
        }}
      />
      <PlanNewSprintDialog
        open={naming}
        taskCount={1}
        onClose={() => setNaming(false)}
        onSubmit={async ({ title, goal }) => {
          const refused = await act(
            () => planBacklog(client, task.project_id, { taskIds: [task.id], newSprint: { title, goal } }),
            `Planned into ${title}.`,
          );
          if (!refused) setNaming(false);
          return refused;
        }}
      />
    </Surface>
  );
}
