import React, { useEffect, useId, useState } from "react";

import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { humanize } from "../../ui/format";
import { DefinitionDialog } from "./DefinitionDialog";

function Ticks({ legend, names, chosen, onChange, label = (name) => name }) {
  function toggle(name) {
    onChange(chosen.includes(name) ? chosen.filter((entry) => entry !== name) : [...chosen, name]);
  }
  return (
    <fieldset className="ticks">
      <legend className="visually-hidden">{legend}</legend>
      {names.map((name) => (
        <label key={name} className="ticks__label">
          <input type="checkbox" className="checkbox" checked={chosen.includes(name)} onChange={() => toggle(name)} />
          {label(name)}
        </label>
      ))}
    </fieldset>
  );
}

// The choice that opens a field for a model the list does not have.
const OTHER = "_other";

/**
 * One model of a role: chosen from the project's list, or typed when the list
 * does not have it. The first model may be left to the project's default; a
 * model it moves up to is always named.
 */
function ModelPicker({ label, value, models, defaultLabel, onChange, onRemove }) {
  const id = useId();
  // A model the list does not have is typed; so is one just picked as "Type a model id…".
  const [typing, setTyping] = useState(false);
  const other = typing || (Boolean(value) && !models.includes(value));
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className="field__input"
        value={other ? OTHER : value}
        onChange={(event) => {
          const picked = event.target.value;
          setTyping(picked === OTHER);
          onChange(picked === OTHER ? "" : picked);
        }}
      >
        {defaultLabel !== null ? <option value="">{defaultLabel}</option> : <option value="">Choose a model</option>}
        {models.map((entry) => (
          <option key={entry} value={entry}>
            {entry}
          </option>
        ))}
        <option value={OTHER}>Type a model id…</option>
      </select>
      {other ? (
        <input
          className="field__input"
          aria-label={`${label} id`}
          placeholder="Model id, as the agent program takes it"
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : null}
      {onRemove ? (
        <Button inRow variant="quiet" onClick={onRemove}>
          Remove {label.toLowerCase()}
        </Button>
      ) : null}
    </div>
  );
}

/**
 * One role, as a form: what it is called, the model, the tools, how its run
 * ends, its limits and its prompt. `role` is the role being edited; with
 * `isNew` it is the role a new one starts as a copy of.
 */
export function RoleEditor({ open, projectId, role, isNew = false, vocabulary, onClose, onSaved }) {
  const escalateId = useId();
  const endsId = useId();
  const everyId = useId();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  // Its models, cheapest first; the first may be empty (the project's default).
  const [models, setModels] = useState([""]);
  const [escalateAfter, setEscalateAfter] = useState("2");
  const [every, setEvery] = useState(false);
  const [tools, setTools] = useState([]);
  const [ends, setEnds] = useState("done");
  const [decisions, setDecisions] = useState([]);
  const [minutes, setMinutes] = useState("");
  const [cost, setCost] = useState("");
  const [prompt, setPrompt] = useState("");

  useEffect(() => {
    if (!open || !role) return;
    setName(isNew ? "" : role.name);
    setDescription(role.description);
    setModels(role.models?.length ? role.models : role.model ? [role.model] : [""]);
    setEscalateAfter(String(role.escalate_after ?? 2));
    setEvery(role.tools.every);
    setTools(role.tools.chosen);
    setEnds(role.ends);
    setDecisions(role.decisions);
    setMinutes(String(role.timeout_minutes));
    setCost(String(role.max_cost_usd));
    setPrompt(role.prompt);
    // The role is read again while the dialog is open; only a different role starts the form over.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, role?.id, isNew]);

  if (!role) return null;
  const known = vocabulary.tools[role.backend] ?? [];

  function fields() {
    const timeout = Number(minutes);
    const limit = Number(cost);
    const named = models.map((entry) => entry.trim());
    const failures = Number(escalateAfter);
    if (!name.trim()) throw new Error("A role needs a name.");
    if (named.slice(1).some((entry) => !entry)) throw new Error("Name each model it moves up to, or remove it.");
    if (named.length > 1 && !named[0]) throw new Error("Name the first model before the ones it moves up to.");
    if (new Set(named).size !== named.length) throw new Error("A model is listed once; it moves up to a different model.");
    if (!Number.isInteger(failures) || failures < 1) throw new Error("Failures before it moves up are a whole number, 1 or more.");
    if (!Number.isInteger(timeout) || timeout <= 0) throw new Error("The time limit is a whole number of minutes.");
    if (!(limit > 0)) throw new Error("The cost limit is a number above zero.");
    if (ends === "decides" && !decisions.length) throw new Error("Tick at least one decision it may give.");
    return {
      name: name.trim(),
      description: description.trim(),
      models: named.filter(Boolean),
      escalate_after: failures,
      tools: { every, chosen: every ? [] : tools },
      ends,
      decisions: ends === "decides" ? decisions : [],
      timeout_minutes: timeout,
      max_cost_usd: limit,
      prompt,
    };
  }

  return (
    <DefinitionDialog
      open={open}
      kind="role"
      projectId={projectId}
      definition={isNew ? null : role}
      copyOf={role.id}
      name={name}
      fields={fields}
      onClose={onClose}
      onSaved={onSaved}
    >
      <Field label="Name" value={name} onChange={(event) => setName(event.target.value)} data-autofocus />
      <Field label="What it does" value={description} onChange={(event) => setDescription(event.target.value)} />
      <ModelPicker
        // A different role starts the pickers over, so a typed model id is read again.
        key={`${role.id}-${isNew}-first`}
        label="Model"
        value={models[0] ?? ""}
        models={vocabulary.models}
        defaultLabel={
          vocabulary.default_model
            ? `The project's default, ${vocabulary.default_model}`
            : projectId
              ? "The project's default"
              : "Each project's default"
        }
        onChange={(value) => setModels((all) => [value, ...all.slice(1)])}
      />
      {models.slice(1).map((entry, index) => (
        <ModelPicker
          key={`${role.id}-${isNew}-${index}`}
          label={`Moves up to ${index + 1}`}
          value={entry}
          models={vocabulary.models}
          defaultLabel={null}
          onChange={(value) => setModels((all) => all.map((one, at) => (at === index + 1 ? value : one)))}
          onRemove={() => setModels((all) => all.filter((_, at) => at !== index + 1))}
        />
      ))}
      <div className="field">
        <Button inRow variant="quiet" onClick={() => setModels((all) => [...all, ""])}>
          Add a model it moves up to
        </Button>
        {models.length > 1 ? (
          <>
            <label className="field__label" htmlFor={escalateId}>
              Failures on one model before it moves up
            </label>
            <input
              id={escalateId}
              className="field__input"
              inputMode="numeric"
              value={escalateAfter}
              onChange={(event) => setEscalateAfter(event.target.value)}
            />
            <span className="field__hint">
              Cheapest first. The run ended without a result, the review sent it back or the tests failed: that is a failure.
              After the last model fails that many times, the task waits for a person.
            </span>
          </>
        ) : (
          <span className="field__hint">With one model it never moves up.</span>
        )}
      </div>

      <div className="field">
        <span className="field__label">Tools</span>
        <label className="ticks__label" htmlFor={everyId}>
          <input
            id={everyId}
            type="checkbox"
            className="checkbox"
            checked={every}
            onChange={(event) => setEvery(event.target.checked)}
          />
          Every tool the agent program has
        </label>
        {every ? null : <Ticks legend="Tools it may use" names={known} chosen={tools} onChange={setTools} />}
        {!every && !tools.length ? <span className="field__hint">With none ticked it has no tool at all.</span> : null}
      </div>

      <div className="field">
        <label className="field__label" htmlFor={endsId}>
          Its run ends when
        </label>
        <select id={endsId} className="field__input" value={ends} onChange={(event) => setEnds(event.target.value)}>
          <option value="done">It says it is done</option>
          <option value="decides">It gives a decision</option>
        </select>
        {ends === "decides" ? (
          <Ticks
            legend="Decisions it may give"
            names={vocabulary.decisions}
            chosen={decisions}
            onChange={setDecisions}
            label={humanize}
          />
        ) : null}
      </div>

      <div className="field-pair">
        <Field label="Time limit, minutes" inputMode="numeric" value={minutes} onChange={(event) => setMinutes(event.target.value)} />
        <Field label="Cost limit, dollars" inputMode="decimal" value={cost} onChange={(event) => setCost(event.target.value)} />
      </div>

      <Field
        label="Prompt"
        hint={
          ends === "decides"
            ? "It must tell the agent to end with each decision in capitals, for example DENY: <reason>."
            : "It must tell the agent to end with {completion_marker}."
        }
        multiline
        className="definition__prompt"
        spellCheck={false}
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
      />
    </DefinitionDialog>
  );
}
