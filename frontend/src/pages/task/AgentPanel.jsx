import React, { useEffect, useId, useMemo, useRef, useState } from "react";

import { useDataRefresh } from "../../api/ApiProvider";
import { getRunOutput, listTaskRuns } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { useOverlay } from "../../app/manager";
import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { StatusDot } from "../../ui/StatusDot";
import { wrapTab } from "../../ui/focus";
import { formatDayTime, formatDuration, formatMoney, humanize } from "../../ui/format";
import { stageOf } from "../sprint/taskStage";
import { narrate } from "./runWords";
import { RunLine, withDays } from "./RunStory";
import { runBy, runResult, runSeconds } from "../shared/activityWords";
import { agentAtWork, noteState, TellAgent } from "./TellAgent";
import { useTaskPulse } from "./useTaskPulse";

import "../../styles/manager.css";

/** How near the end of the thread still counts as at the end, in CSS pixels of scroll. */
const FOLLOW_SLACK = 24;
// The conversation shows the latest steps; earlier ones are on the Activity tab.
export const STEPS_SHOWN = 25;

const HUMAN_GATE = "_builtin:human_gate";

// Runs that only hold the record of something done to the task (filed, planned,
// cancelled, stopped by the engine). They are not steps; the Activity tab lists them.
const RECORD_KEEPERS = new Set(["api", "cli", "engine", "orchestrator"]);
const isStep = (run) => !RECORD_KEEPERS.has(run.backend ?? run.agent_backend);

// What the conversation already says elsewhere: the step's own line (the step,
// the model, how it ended, the time and the cost) and a person's words, which
// have their own place. The Activity tab keeps the full record.
const SAID_ELSEWHERE = new Set([
  "human.message",
  "human.message_delivered",
  "workflow.step_started",
  "workflow.model_selected",
  "engine.role_policy",
  "agent.started",
  "agent.completed",
  "workflow.step_completed",
  "workflow.transition",
]);

/**
 * What a step said and did, in the order it happened. `pulse` grows while
 * the step is running and printing, and each change reads it again.
 */
function StepStory({ run, pulse }) {
  const output = useResource(["run-output", run.id], (client, options) => getRunOutput(client, run.id, options));
  const reload = output.reload;
  useEffect(() => {
    if (pulse) reload();
  }, [pulse, reload]);
  if (output.error) {
    return (
      <p className="manager__failure" role="alert">
        {output.error}
      </p>
    );
  }
  if (!output.data) return <p className="manager__quiet">Reading what it did.</p>;
  const told = output.data.transcript.filter((entry) => !SAID_ELSEWHERE.has(entry.kind));
  const lines = withDays(narrate(told), run.started_at);
  if (lines.length === 0) {
    return run.status === "running" ? <p className="manager__quiet">Nothing to read yet.</p> : null;
  }
  return (
    <ol className="run-story agent__story" aria-label={`What ${humanize(run.step).toLowerCase()} did`}>
      {lines.map((line, index) => (
        <RunLine key={index} line={line} />
      ))}
    </ol>
  );
}

/**
 * One step of the task in the conversation: a line that says which step, how
 * it ended, who did it, how long it took and what it cost, and under it, when
 * open, what was said and done.
 */
function Step({ run, task, open, pulse, onToggle }) {
  const bodyId = useId();
  const result = runResult(run);
  const facts = [runBy(run, task), formatDuration(runSeconds(run)), run.cost_usd ? formatMoney(run.cost_usd) : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className="agent__step">
      <button type="button" className="agent__step-head" aria-expanded={open} aria-controls={bodyId} onClick={onToggle}>
        <span className="agent__step-name">{humanize(run.step)}</span>
        <span className={`agent__step-result tone-${result.tone}`}>{result.word}</span>
        <span className="agent__step-facts">{facts}</span>
      </button>
      {result.note ? (
        <p className="agent__step-note" title={result.note}>
          {result.note}
        </p>
      ) : null}
      {open ? (
        <div id={bodyId} className="agent__step-body">
          <StepStory run={run} pulse={pulse} />
        </div>
      ) : null}
    </li>
  );
}

/** Something a person told the agent, where it was said. */
function Said({ note }) {
  const state = noteState(note);
  return (
    <li className="agent__said">
      <span className="agent__said-who">You · {formatDayTime(note.recorded_at)}</span>
      <p className="agent__said-text">{note.text}</p>
      <StatusDot tone={state.tone}>{state.word}</StatusDot>
    </li>
  );
}

const moment = (entry) => String(entry.note ? entry.note.recorded_at : entry.run.started_at || entry.run.finished_at || "");

/**
 * The conversation with the agents working on one task, in the side bar of a
 * task page (the place the manager has on a project or a sprint): the steps
 * in order, oldest first, what each said and did, what a person told them
 * where it was said, and at the bottom the box to tell the agent something.
 *
 * The step in progress is open and read again as it prints; with none in
 * progress the last step an agent or the engine did is open. The thread stays
 * on its latest line while the person is at the end of it.
 */
export function AgentPanel({ task, onClose }) {
  const headingId = useId();
  const overlay = useOverlay();
  const { refresh } = useDataRefresh();
  const taskId = task?.id ?? null;
  const runs = useResource(
    ["task-runs", taskId, "conversation"],
    (client, options) => listTaskRuns(client, taskId, { limit: STEPS_SHOWN, offset: 0, ...options }),
    { enabled: Boolean(taskId) },
  );
  const [toggled, setToggled] = useState(() => new Set());
  const root = useRef(null);
  const thread = useRef(null);
  const atEnd = useRef(true);

  const entries = useMemo(() => {
    // The API lists runs newest first; a conversation reads oldest first.
    const steps = [...(runs.data?.items ?? [])].filter(isStep).reverse().map((run) => ({ run }));
    const said = (task?.guidance ?? []).map((note) => ({ note }));
    return [...steps, ...said].sort((a, b) => moment(a).localeCompare(moment(b)));
  }, [runs.data, task]);
  const steps = entries.filter((entry) => entry.run).map((entry) => entry.run);
  const inProgress = steps.find((run) => run.status === "running") ?? null;
  const atWork = steps.find(agentAtWork) ?? null;
  const shown = inProgress ?? [...steps].reverse().find((run) => run.role_id !== HUMAN_GATE) ?? steps[steps.length - 1] ?? null;
  const pulse = useTaskPulse(taskId, Boolean(inProgress));

  // Stay on the latest line as the thread grows, unless the person scrolled up to read.
  useEffect(() => {
    const node = thread.current;
    if (!node || typeof MutationObserver === "undefined") return undefined;
    const follow = () => {
      if (atEnd.current) node.scrollTop = node.scrollHeight;
    };
    follow();
    const observer = new MutationObserver(follow);
    observer.observe(node, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, []);

  // Covering the page, the bar is a dialog: focus goes into it and comes back.
  useEffect(() => {
    if (!overlay) return undefined;
    const previous = document.activeElement;
    (root.current?.querySelector("textarea:not([disabled])") || root.current?.querySelector(".manager__close"))?.focus();
    return () => {
      if (previous && typeof previous.focus === "function" && document.contains(previous)) previous.focus();
    };
  }, [overlay]);

  function onKeyDown(event) {
    if (!overlay || !root.current?.contains(event.target)) return;
    if (event.key === "Escape") {
      if (event.defaultPrevented) return;
      event.preventDefault();
      onClose();
      return;
    }
    wrapTab(event, root.current);
  }

  function onScroll() {
    const node = thread.current;
    if (node) atEnd.current = node.scrollHeight - node.scrollTop - node.clientHeight <= FOLLOW_SLACK;
  }

  const finished = task ? task.status === "done" || task.status === "cancelled" : false;
  const isOpen = (run) => (run === shown) !== toggled.has(run.id);
  const toggle = (run) =>
    setToggled((previous) => {
      const next = new Set(previous);
      if (next.has(run.id)) next.delete(run.id);
      else next.add(run.id);
      return next;
    });
  const earlier = (runs.data?.total ?? 0) - (runs.data?.items.length ?? 0);

  return (
    <section
      className="manager agent"
      aria-labelledby={headingId}
      aria-modal={overlay ? "true" : undefined}
      role={overlay ? "dialog" : undefined}
      ref={root}
      onKeyDown={onKeyDown}
    >
      <div className="manager__head">
        <h2 className="manager__title" id={headingId}>
          Agent
        </h2>
        {task ? <span className="manager__project">{task.task_key || task.title}</span> : null}
        {task ? (
          <span className="manager__where">
            {inProgress ? `${humanize(inProgress.step)} is running` : stageOf(task).word}
          </span>
        ) : null}
        <Button variant="quiet" inRow className="manager__close" onClick={onClose}>
          Close
        </Button>
      </div>

      <div className="manager__thread" role="log" aria-live="polite" ref={thread} onScroll={onScroll}>
        {runs.error ? (
          <p className="manager__failure" role="alert">
            {runs.error}
          </p>
        ) : null}
        {!runs.error && (!task || !runs.data) ? <p className="manager__quiet">Loading the conversation.</p> : null}
        {task && runs.data && entries.length === 0 ? (
          <p className="manager__quiet">No agent has worked on this task yet.</p>
        ) : null}
        {earlier > 0 ? (
          <Link className="manager__quiet" href={paths.taskActivity(taskId)}>
            {earlier} earlier {earlier === 1 ? "step" : "steps"}
          </Link>
        ) : null}
        {entries.length ? (
          <ol className="agent__thread" aria-label="Steps and what was said">
            {entries.map((entry) =>
              entry.note ? (
                <Said key={entry.note.event_id} note={entry.note} />
              ) : (
                <Step
                  key={entry.run.id}
                  run={entry.run}
                  task={task}
                  open={isOpen(entry.run)}
                  pulse={entry.run === inProgress ? pulse : 0}
                  onToggle={() => toggle(entry.run)}
                />
              ),
            )}
          </ol>
        ) : null}
      </div>

      {task && !finished ? (
        <div className="manager__composer">
          <TellAgent task={task} running={atWork} onSent={refresh} />
        </div>
      ) : null}
    </section>
  );
}
