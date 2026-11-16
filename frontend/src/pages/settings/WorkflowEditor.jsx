import React, { useEffect, useId, useRef, useState } from "react";

import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { humanize } from "../../ui/format";
import { DefinitionDialog } from "./DefinitionDialog";
import { GATE_POLICY, idFromName, outcomeWords } from "./definitionWords";

const GATE = "_builtin:human_gate";
const LAST = "_builtin:mark_done";

/**
 * One workflow, as its steps in order. Each step has a name, what does it,
 * and for each way it can end, the step that follows. A way to end with no
 * step chosen stops the task for a person.
 *
 * Steps are held by a key of their own, so renaming a step keeps what points
 * at it; the ids are made from the names when the form is saved.
 */
export function WorkflowEditor({ open, projectId, workflow, isNew = false, vocabulary, onClose, onSaved }) {
  const [name, setName] = useState("");
  const [steps, setSteps] = useState([]);
  const nextKey = useRef(0);
  const stepsId = useId();

  useEffect(() => {
    if (!open || !workflow) return;
    setName(isNew ? "" : workflow.name);
    const keys = Object.fromEntries(workflow.steps.map((step, index) => [step.id, `k${index}`]));
    nextKey.current = workflow.steps.length;
    setSteps(
      workflow.steps.map((step) => ({
        key: keys[step.id],
        label: humanize(step.id),
        role: step.role,
        policy: step.policy ?? "",
        then: Object.fromEntries(
          Object.entries(step.then).map(([outcome, target]) => [
            outcome,
            { to: keys[target.to] ?? "", carry: Boolean(target.carry_output) },
          ]),
        ),
      })),
    );
    // Only a different workflow starts the form over.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workflow?.id, isNew]);

  if (!workflow) return null;
  const doneBy = (role) => vocabulary.done_by.find((entry) => entry.role === role);

  const change = (key, patch) => setSteps(steps.map((step) => (step.key === key ? { ...step, ...patch } : step)));
  const changeThen = (step, outcome, patch) =>
    change(step.key, { then: { ...step.then, [outcome]: { to: "", carry: false, ...step.then[outcome], ...patch } } });

  function move(index, by) {
    const next = [...steps];
    const [taken] = next.splice(index, 1);
    next.splice(index + by, 0, taken);
    setSteps(next);
  }

  function add() {
    const key = `k${nextKey.current++}`;
    const first = vocabulary.done_by.find((entry) => !entry.role.startsWith("_builtin:")) ?? vocabulary.done_by[0];
    // Before the step that marks the task done, if the workflow ends with one.
    const at = steps.length && steps[steps.length - 1].role === LAST ? steps.length - 1 : steps.length;
    const after = steps[at];
    const good = first.outcomes[0];
    const then = after && good ? { [good]: { to: after.key, carry: false } } : {};
    // The step before it led to the step it now stands in front of: it leads here instead.
    const before = steps.slice(0, at).map((step, index) => {
      if (index !== at - 1 || !after) return step;
      const rerouted = Object.fromEntries(
        Object.entries(step.then).map(([outcome, target]) => [outcome, target.to === after.key ? { ...target, to: key } : target]),
      );
      return { ...step, then: rerouted };
    });
    setSteps([...before, { key, label: "", role: first.role, policy: "", then }, ...steps.slice(at)]);
  }

  function fields() {
    if (!name.trim()) throw new Error("A workflow needs a name.");
    const ids = {};
    for (const step of steps) {
      const id = idFromName(step.label);
      if (!id) throw new Error("Every step needs a name that starts with a letter.");
      if (Object.values(ids).includes(id)) throw new Error(`Two steps are called ${step.label.trim()}.`);
      ids[step.key] = id;
    }
    return {
      name: name.trim(),
      steps: steps.map((step) => {
        const outcomes = doneBy(step.role)?.outcomes ?? [];
        const then = {};
        for (const outcome of outcomes) {
          const target = step.then[outcome];
          if (target?.to && ids[target.to]) then[outcome] = { to: ids[target.to], carry_output: target.carry };
        }
        return { id: ids[step.key], role: step.role, policy: step.role === GATE ? step.policy || null : null, then };
      }),
    };
  }

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
    >
      <Field label="Name" value={name} onChange={(event) => setName(event.target.value)} data-autofocus />
      <div className="steps-editor__title">
        <span className="field__label" id={stepsId}>
          Steps
        </span>
        <span className="steps-editor__columns" aria-hidden="true">
          <span />
          <span>Step</span>
          <span>Done by</span>
        </span>
      </div>
      <ol className="steps-editor" aria-labelledby={stepsId}>
        {steps.map((step, index) => {
          const title = step.label.trim() || `step ${index + 1}`;
          const outcomes = step.role === LAST ? [] : (doneBy(step.role)?.outcomes ?? []);
          return (
            <li key={step.key} className="steps-editor__step">
              <div className="steps-editor__head">
                <span className="steps-editor__number">
                  {index + 1}
                  {index === 0 ? <span className="steps-editor__start">start</span> : null}
                </span>
                <Field
                  label={`Name of step ${index + 1}`}
                  hideLabel
                  placeholder="Step name"
                  value={step.label}
                  onChange={(event) => change(step.key, { label: event.target.value })}
                />
                <select
                  className="field__input"
                  aria-label={`Who does ${title}`}
                  value={step.role}
                  onChange={(event) => change(step.key, { role: event.target.value })}
                >
                  {vocabulary.done_by.map((entry) => (
                    <option key={entry.role} value={entry.role}>
                      {entry.label}
                    </option>
                  ))}
                </select>
                <span className="steps-editor__moves">
                  <Button variant="quiet" inRow disabled={index === 0} aria-label={`Move ${title} up`} onClick={() => move(index, -1)}>
                    Up
                  </Button>
                  <Button
                    variant="quiet"
                    inRow
                    disabled={index === steps.length - 1}
                    aria-label={`Move ${title} down`}
                    onClick={() => move(index, 1)}
                  >
                    Down
                  </Button>
                  <Button
                    variant="quiet"
                    inRow
                    aria-label={`Remove ${title}`}
                    onClick={() => setSteps(steps.filter((entry) => entry.key !== step.key))}
                  >
                    Remove
                  </Button>
                </span>
              </div>
              {step.role === GATE ? (
                <div className="steps-editor__then steps-editor__then--wide">
                  <label className="steps-editor__pick">
                    <span>It stops for a person when</span>
                    <select
                      className="field__input"
                      value={step.policy}
                      onChange={(event) => change(step.key, { policy: event.target.value })}
                    >
                      <option value="">always</option>
                      {vocabulary.gate_policies.map((policy) => (
                        <option key={policy} value={policy}>
                          {GATE_POLICY[policy] ?? policy}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              ) : null}
              {outcomes.map((outcome) => {
                const target = step.then[outcome] ?? { to: "", carry: false };
                const words = outcomeWords(step.role, outcome);
                return (
                  <div key={outcome} className="steps-editor__then">
                    <label className="steps-editor__pick">
                      <span>When {words}</span>
                      <select
                        className="field__input"
                        aria-label={`${title}: when ${words}, go to`}
                        value={steps.some((entry) => entry.key === target.to) ? target.to : ""}
                        onChange={(event) => changeThen(step, outcome, { to: event.target.value })}
                      >
                        <option value="">stop and wait for a person</option>
                        {steps
                          .filter((entry) => entry.key !== step.key)
                          .map((entry) => (
                            <option key={entry.key} value={entry.key}>
                              go to {steps.indexOf(entry) + 1} · {entry.label.trim() || "unnamed step"}
                            </option>
                          ))}
                      </select>
                    </label>
                    {target.to ? (
                      <label className="ticks__label">
                        <input
                          type="checkbox"
                          className="checkbox"
                          aria-label={`${title}: when ${words}, tell the next step what this step said`}
                          checked={target.carry}
                          onChange={(event) => changeThen(step, outcome, { carry: event.target.checked })}
                        />
                        and tell it what this step said
                      </label>
                    ) : (
                      <span />
                    )}
                  </div>
                );
              })}
            </li>
          );
        })}
      </ol>
      <div>
        <Button variant="quiet" onClick={add}>
          Add a step
        </Button>
      </div>
    </DefinitionDialog>
  );
}
