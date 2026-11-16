import React, { useEffect, useId, useState } from "react";

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

/**
 * One role, as a form: what it is called, the model, the tools, how its run
 * ends, its limits and its prompt. `role` is the role being edited; with
 * `isNew` it is the role a new one starts as a copy of.
 */
export function RoleEditor({ open, projectId, role, isNew = false, vocabulary, onClose, onSaved }) {
  const modelsId = useId();
  const endsId = useId();
  const everyId = useId();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [model, setModel] = useState("");
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
    setModel(role.model);
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
    if (!name.trim()) throw new Error("A role needs a name.");
    if (!Number.isInteger(timeout) || timeout <= 0) throw new Error("The time limit is a whole number of minutes.");
    if (!(limit > 0)) throw new Error("The cost limit is a number above zero.");
    if (ends === "decides" && !decisions.length) throw new Error("Tick at least one decision it may give.");
    return {
      name: name.trim(),
      description: description.trim(),
      model: model.trim(),
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
      <Field
        label="Model"
        hint={
          vocabulary.default_model
            ? `Empty uses the project's default, ${vocabulary.default_model}.`
            : projectId
              ? "Empty uses the project's default."
              : "Empty uses each project's default."
        }
        list={modelsId}
        value={model}
        onChange={(event) => setModel(event.target.value)}
      />
      <datalist id={modelsId}>
        {vocabulary.models.map((entry) => (
          <option key={entry} value={entry} />
        ))}
      </datalist>

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
