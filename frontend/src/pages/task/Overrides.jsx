import React, { useEffect, useId, useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { setTaskOverrides } from "../../api/tasks";
import { Button } from "../../ui/Button";
import { SectionHeading } from "../../ui/SectionHeading";
import {
  applyOverrides,
  currentGateOverride,
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

function StepRow({ step, value, onChange }) {
  const id = useId();
  return (
    <div className="overrides__row">
      <label className="field__label" htmlFor={id}>
        Model for {step.label.toLowerCase()}
      </label>
      <input
        id={id}
        className="field__input"
        type="text"
        placeholder="No override"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
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
  const gates = overrideGates(workflow);
  const steps = overrideSteps(workflow);
  const stored = JSON.stringify(task.executor_overrides ?? {});
  const [gateValues, setGateValues] = useState({});
  const [modelValues, setModelValues] = useState({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);

  // Start from what the task has; again whenever the task is read anew.
  useEffect(() => {
    const overrides = task.executor_overrides ?? {};
    setGateValues(Object.fromEntries(gates.map((gate) => [gate.policy, currentGateOverride(task, gate.policy)])));
    setModelValues(Object.fromEntries(steps.map((step) => [step.id, overrides.models?.[step.id] ?? ""])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stored, workflow]);

  if (!gates.length && !steps.length) return null;

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      await setTaskOverrides(client, task.id, applyOverrides(task.executor_overrides, { gates: gateValues, models: modelValues }));
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
            onChange={(value) => setModelValues((all) => ({ ...all, [step.id]: value }))}
          />
        ))}
        <div className="overrides__actions">
          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save overrides"}
          </Button>
          {notice ? (
            <span className={notice.error ? "notice notice--error" : "notice"} role={notice.error ? "alert" : "status"}>
              {notice.text}
            </span>
          ) : null}
        </div>
      </form>
    </section>
  );
}
