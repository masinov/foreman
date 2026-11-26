import React, { useId, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { getProjectDefinitions } from "../../api/definitions";
import { setTaskOverrides } from "../../api/tasks";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { SectionHeading } from "../../ui/SectionHeading";
import { useNotice } from "../../ui/Toast";
import {
  applyOverrides,
  currentGateOverride,
  currentStart,
  gateChoices,
  overrideGates,
  overrideSteps,
} from "./taskWords";

function GateRow({ gate, value, onChange }) {
  const id = useId();
  return (
    <div className="overrides__row">
      <label className="field__label" htmlFor={id}>
        Who decides {gate.label.toLowerCase()}
      </label>
      <select id={id} className="field__input" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">No override</option>
        {gateChoices().map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.word}
          </option>
        ))}
      </select>
    </div>
  );
}

/** One of the models the project has configured; a model is added on a role, not here. */
function StepRow({ step, value, models, onChange }) {
  const id = useId();
  // What the task already has stays choosable even if no role names it any more.
  const choices = value && !models.includes(value) ? [value, ...models] : models;
  return (
    <div className="overrides__row">
      <label className="field__label" htmlFor={id}>
        Model for {step.label.toLowerCase()}
      </label>
      <select id={id} className="field__input" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">No override</option>
        {choices.map((model) => (
          <option key={model} value={model}>
            {model}
          </option>
        ))}
      </select>
    </div>
  );
}

/** The model every step starts on among its role's models, when not the first of each. */
function StartRow({ value, models, onChange }) {
  const id = useId();
  const choices = value && !models.includes(value) ? [value, ...models] : models;
  return (
    <div className="overrides__row">
      <label className="field__label" htmlFor={id}>
        Start on
      </label>
      <select id={id} className="field__input" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">The first model of each role</option>
        {choices.map((model) => (
          <option key={model} value={model}>
            {model}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Overrides for this task: who decides at its gates, and which model runs a
 * step. Only what is set here applies to this task; empty means the
 * project's setting or the role's model. Saved over PATCH executor_overrides.
 */
export function Overrides({ task, workflow, onSaved }) {
  const client = useApiClient();
  // The models to choose from are the project's: its default, the ones its roles name, the known ones.
  const definitions = useResource(
    ["project-definitions", task.project_id],
    (api, options) => getProjectDefinitions(api, task.project_id, options),
    { enabled: Boolean(task.project_id) },
  );
  const models = definitions.data?.vocabulary.models ?? [];
  const gates = overrideGates(workflow);
  const steps = overrideSteps(workflow);
  const stored = JSON.stringify(task.executor_overrides ?? {});
  // What can be overridden, as text: the same workflow read again is the
  // same text, so a background refresh does not wipe what is being typed.
  const shape = JSON.stringify([gates.map((gate) => gate.policy), steps.map((step) => step.id)]);
  const startGates = () => Object.fromEntries(gates.map((gate) => [gate.policy, currentGateOverride(task, gate.policy)]));
  const startModels = () =>
    Object.fromEntries(steps.map((step) => [step.id, task.executor_overrides?.models?.[step.id] ?? ""]));
  const [gateValues, setGateValues] = useState(startGates);
  const [modelValues, setModelValues] = useState(startModels);
  const [startValue, setStartValue] = useState(() => currentStart(task));
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useNotice();

  // Start from what the task has; again only when what it has changed. Done
  // while rendering, not in an effect, so it cannot land on top of an edit
  // made right after the first render.
  const read = `${stored}\n${shape}`;
  const [shown, setShown] = useState(read);
  if (shown !== read) {
    setShown(read);
    setGateValues(startGates());
    setModelValues(startModels());
    setStartValue(currentStart(task));
  }

  if (!gates.length && !steps.length) return null;

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      await setTaskOverrides(client, task.id, applyOverrides(task.executor_overrides, { gates: gateValues, models: modelValues, start: startValue === currentStart(task) ? undefined : startValue }));
      setNotice({ error: false, text: "Saved." });
      onSaved();
    } catch (error) {
      setNotice({ error: true, text: errorSentence(error) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="task-section" aria-labelledby="task-overrides">
      <SectionHeading id="task-overrides" title="Overrides for this task" />
      <form className="overrides" onSubmit={save} noValidate>
        {gates.map((gate) => (
          <GateRow
            key={gate.policy}
            gate={gate}
            value={gateValues[gate.policy] ?? ""}
            onChange={(value) => setGateValues((all) => ({ ...all, [gate.policy]: value }))}
          />
        ))}
        {steps.map((step) => (
          <StepRow
            key={step.id}
            step={step}
            value={modelValues[step.id] ?? ""}
            models={models}
            onChange={(value) => setModelValues((all) => ({ ...all, [step.id]: value }))}
          />
        ))}
        {steps.length ? <StartRow value={startValue} models={models} onChange={setStartValue} /> : null}
        <div className="overrides__actions">
          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save overrides"}
          </Button>
          {notice ? (
            <span className="notice notice--error" role="alert">
              {notice.text}
            </span>
          ) : null}
        </div>
      </form>
    </section>
  );
}
