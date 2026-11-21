import React, { useEffect, useId, useRef, useState } from "react";

import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { humanize } from "../../ui/format";
import { DefinitionDialog } from "./DefinitionDialog";
import { GATE_POLICY, idFromName, outcomeWords, shortOutcome } from "./definitionWords";
import { WorkflowGraph } from "./WorkflowGraph";

const GATE = "_builtin:human_gate";
const LAST = "_builtin:mark_done";

// Where a way of ending leads, besides another step (held by that step's key).
const NEXT = "_next"; // the step below, or the end after the last step
const STOP = ""; // nowhere: the task stops and waits for a user
const END = "_end"; // straight to the end (only kept if a workflow already says so)

/**
 * One workflow, as a sequence. A task enters at the first step and leaves
 * after the last, done. Each step has a name and who does it. The way a step
 * ends well leads to the step below it unless said otherwise; every other way
 * it can end says where the task goes instead: back to an earlier step, ahead
 * to a later one, or nowhere, which stops it for a person.
 *
 * What is saved is the engine's form: steps and routes, with the step that
 * marks the task done added at the end (ADR-0027 says what a workflow must
 * satisfy; the server refuses one that does not, with the reason). A step an
 * agent does is told what the step before it said whenever the task did not
 * simply move on.
 *
 * Steps are held by a key of their own, so renaming a step keeps what points
 * at it; the ids are made from the names when the form is saved.
 */
export function WorkflowEditor({ open, projectId, workflow, isNew = false, vocabulary, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [steps, setSteps] = useState([]);
  // Whether the workflow ends with the one step that marks a task done, which
  // the form then keeps out of sight as "the end".
  const [hasEnd, setHasEnd] = useState(true);
  const nextKey = useRef(0);
  const whoId = useId();
  // The step shown beside the graph, by its key.
  const [selected, setSelected] = useState(null);

  const doneBy = (role) => vocabulary?.done_by.find((entry) => entry.role === role);
  const outcomesOf = (role) => (role === LAST ? [] : (doneBy(role)?.outcomes ?? []));
  // A step that may change the code: an agent that ends by saying it is done.
  const works = (role) => !role.startsWith("_builtin:") && outcomesOf(role).join() === "done";

  useEffect(() => {
    if (!open || !workflow) return;
    setName(isNew ? "" : workflow.name);
    const all = workflow.steps;
    const ends = all.filter((step) => step.role === LAST);
    const closing = ends.length === 1 && all[all.length - 1].role === LAST && all.length > 1 ? all[all.length - 1] : null;
    const shown = closing ? all.slice(0, -1) : all;
    const keys = Object.fromEntries(shown.map((step, index) => [step.id, `k${index}`]));
    nextKey.current = shown.length;
    setHasEnd(Boolean(closing));
    setSelected(shown.length ? keys[shown[0].id] : null);
    setSteps(
      shown.map((step, index) => {
        const below = shown[index + 1]?.id ?? closing?.id;
        const outcomes = step.role === LAST ? [] : (vocabulary.done_by.find((entry) => entry.role === step.role)?.outcomes ?? []);
        const then = {};
        for (const outcome of outcomes) {
          const to = step.then[outcome]?.to;
          if (!to) then[outcome] = STOP;
          else if (outcome === outcomes[0] && to === below) then[outcome] = NEXT;
          else if (closing && to === closing.id) then[outcome] = END;
          else then[outcome] = keys[to] ?? STOP;
        }
        return { key: keys[step.id], label: humanize(step.id), role: step.role, policy: step.policy ?? "", then };
      }),
    );
    // Only a different workflow starts the form over.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workflow?.id, isNew]);

  if (!workflow) return null;

  /** Where each way of ending leads for a step put at `index`: on, and otherwise back to the work. */
  function defaults(role, index, list) {
    const earlier = list.slice(0, index).filter((entry) => works(entry.role));
    const back = earlier.length ? earlier[earlier.length - 1].key : STOP;
    return Object.fromEntries(outcomesOf(role).map((outcome, at) => [outcome, at === 0 ? NEXT : back]));
  }

  const change = (key, patch) => setSteps(steps.map((step) => (step.key === key ? { ...step, ...patch } : step)));

  function changeRole(step, index, role) {
    const fresh = defaults(role, index, steps);
    // A way of ending the new doer shares with the old keeps where it led.
    const then = Object.fromEntries(Object.entries(fresh).map(([outcome, to]) => [outcome, step.then[outcome] ?? to]));
    change(step.key, { role, then });
  }

  function move(index, by) {
    const next = [...steps];
    const [taken] = next.splice(index, 1);
    next.splice(index + by, 0, taken);
    setSteps(next);
  }

  function add() {
    const key = `k${nextKey.current++}`;
    const first = vocabulary.done_by.find((entry) => !entry.role.startsWith("_builtin:")) ?? vocabulary.done_by[0];
    setSteps([...steps, { key, label: "", role: first.role, policy: "", then: defaults(first.role, steps.length, steps) }]);
    setSelected(key);
  }

  function remove(key) {
    setSteps(
      steps
        .filter((step) => step.key !== key)
        .map((step) => ({
          ...step,
          then: Object.fromEntries(Object.entries(step.then).map(([outcome, to]) => [outcome, to === key ? STOP : to])),
        })),
    );
  }

  function fields() {
    if (!name.trim()) throw new Error("A workflow needs a name.");
    if (!steps.length) throw new Error("A workflow needs at least one step.");
    const ids = {};
    for (const step of steps) {
      const id = idFromName(step.label);
      if (!id) throw new Error("Every step needs a name that starts with a letter.");
      if (Object.values(ids).includes(id)) throw new Error(`Two steps are called ${step.label.trim()}.`);
      ids[step.key] = id;
    }
    const taken = Object.values(ids);
    const endId = hasEnd ? ["done", "finished", "end_of_workflow"].find((id) => !taken.includes(id)) : null;
    const roleOf = Object.fromEntries(steps.map((step) => [ids[step.key], step.role]));
    const saved = steps.map((step, index) => {
      const outcomes = outcomesOf(step.role);
      const then = {};
      outcomes.forEach((outcome, at) => {
        const chosen = step.then[outcome] ?? STOP;
        let to = null;
        if (chosen === NEXT) to = steps[index + 1] ? ids[steps[index + 1].key] : endId;
        else if (chosen === END) to = endId;
        else if (chosen !== STOP) to = ids[chosen] ?? null;
        if (!to) return;
        // An agent is told what this step said unless the task simply moved on.
        const agent = to !== endId && !roleOf[to].startsWith("_builtin:");
        then[outcome] = { to, carry_output: agent && at !== 0 };
      });
      return { id: ids[step.key], role: step.role, policy: step.role === GATE ? step.policy || null : null, then };
    });
    if (endId) saved.push({ id: endId, role: LAST, policy: null, then: {} });
    return { name: name.trim(), steps: saved };
  }

  const titleOf = (step, index) => step.label.trim() || `step ${index + 1}`;
  const index = Math.max(
    0,
    steps.findIndex((step) => step.key === selected),
  );
  const step = steps[index];
  const below = steps[index + 1];

  // The graph: where each ending of each step leads, as rows of the drawing.
  const rows = steps.map((entry, at) => {
    const routes = [];
    const stops = [];
    const nexts = [];
    let on = false;
    outcomesOf(entry.role).forEach((outcome) => {
      const chosen = entry.then[outcome] ?? STOP;
      const words = shortOutcome(entry.role, outcome);
      let to = null;
      if (chosen === NEXT) to = at + 1 < steps.length || hasEnd ? at + 1 : null;
      else if (chosen === END) to = steps.length;
      else if (chosen !== STOP) to = steps.findIndex((other) => other.key === chosen);
      if (to === at + 1) on = true;
      if (to === null || to < 0) stops.push(words);
      else if (to !== at + 1) routes.push({ to, words });
      else if (outcome !== outcomesOf(entry.role)[0]) nexts.push(words);
    });
    return { key: entry.key, title: titleOf(entry, at), who: doneBy(entry.role)?.label ?? entry.role, on, routes, stops, nexts };
  });

  return (
    <DefinitionDialog
      open={open}
      kind="workflow"
      projectId={projectId}
      definition={isNew ? null : workflow}
      copyOf={workflow.id}
      name={name}
      fields={fields}
      onClose={onClose}
      onSaved={onSaved}
      className="dialog--workflow"
    >
      <Field label="Name" value={name} onChange={(event) => setName(event.target.value)} data-autofocus />
      <div className="wf-editor">
        <div className="wf-editor__graph">
          <div className="wf-editor__heading">
            <span className="field__label">Steps</span>
            <Button onClick={add}>Add a step</Button>
          </div>
          <WorkflowGraph rows={rows} end={hasEnd} selected={step?.key} onSelect={setSelected} label="Steps" />
        </div>
        {step ? (
          <div className="wf-editor__step" role="group" aria-label={`Step ${index + 1}`}>
            <Field
              label="Step name"
              aria-label={`Name of step ${index + 1}`}
              placeholder="Step name"
              value={step.label}
              onChange={(event) => change(step.key, { label: event.target.value })}
            />
            <div className="field">
              <label className="field__label" htmlFor={whoId}>
                Done by
              </label>
              <select
                id={whoId}
                className="field__input"
                aria-label={`Who does ${titleOf(step, index)}`}
                value={step.role}
                onChange={(event) => changeRole(step, index, event.target.value)}
              >
                {vocabulary.done_by
                  .filter((entry) => entry.role !== LAST || !hasEnd || entry.role === step.role)
                  .map((entry) => (
                    <option key={entry.role} value={entry.role}>
                      {entry.label}
                    </option>
                  ))}
              </select>
            </div>
            {step.role === GATE ? (
              <label className="wf-editor__ending">
                <span>It stops for a user when</span>
                <select className="field__input" value={step.policy} onChange={(event) => change(step.key, { policy: event.target.value })}>
                  <option value="">always</option>
                  {vocabulary.gate_policies.map((policy) => (
                    <option key={policy} value={policy}>
                      {GATE_POLICY[policy] ?? policy}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {outcomesOf(step.role).map((outcome, at) => {
              const chosen = step.then[outcome] ?? STOP;
              const words = outcomeWords(step.role, outcome);
              const known = [NEXT, STOP, END].includes(chosen) || steps.some((entry) => entry.key === chosen);
              return (
                <label key={outcome} className="wf-editor__ending">
                  <span>When {words}</span>
                  <select
                    className="field__input"
                    aria-label={`${titleOf(step, index)}: when ${words}`}
                    value={known ? chosen : STOP}
                    onChange={(event) => change(step.key, { then: { ...step.then, [outcome]: event.target.value } })}
                  >
                    {at === 0 || chosen === NEXT ? (
                      <option value={NEXT}>
                        {below
                          ? `on to ${index + 2} · ${titleOf(below, index + 1)}`
                          : hasEnd
                            ? "the task is done"
                            : "stop and wait for a user"}
                      </option>
                    ) : null}
                    {steps.map((entry, other) =>
                      entry.key === step.key || (at === 0 && entry === below) ? null : (
                        <option key={entry.key} value={entry.key}>
                          {other < index ? "back to" : "ahead to"} {other + 1} · {titleOf(entry, other)}
                        </option>
                      ),
                    )}
                    {chosen === END ? <option value={END}>the task is done</option> : null}
                    <option value={STOP}>stop and wait for a user</option>
                  </select>
                </label>
              );
            })}
            <div className="wf-editor__moves">
              <Button variant="quiet" disabled={index === 0} aria-label={`Move ${titleOf(step, index)} up`} onClick={() => move(index, -1)}>
                Move up
              </Button>
              <Button
                variant="quiet"
                disabled={index === steps.length - 1}
                aria-label={`Move ${titleOf(step, index)} down`}
                onClick={() => move(index, 1)}
              >
                Move down
              </Button>
              <Button variant="quiet" aria-label={`Remove ${titleOf(step, index)}`} onClick={() => remove(step.key)}>
                Remove step
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </DefinitionDialog>
  );
}
