import React, { useId, useState } from "react";

import { TASK_TYPES } from "../../api/backlog";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { DECIDERS, RULE_DECISIONS, ruleDecisionLabel, ruleValueWord } from "./settingsWords";

function entriesOf(rules) {
  return Object.entries(rules).flatMap(([taskType, decisions]) =>
    Object.entries(decisions).map(([decision, value]) => ({ taskType, decision, value })),
  );
}

function withRule(rules, { taskType, decision, value }) {
  return { ...rules, [taskType]: { ...(rules[taskType] ?? {}), [decision]: value } };
}

function withoutRule(rules, { taskType, decision }) {
  const { [decision]: _removed, ...rest } = rules[taskType] ?? {};
  const { [taskType]: _type, ...others } = rules;
  return Object.keys(rest).length ? { ...others, [taskType]: rest } : others;
}

function AddRule({ onAdd, onCancel }) {
  const ids = [useId(), useId(), useId()];
  const [taskType, setTaskType] = useState(TASK_TYPES[0]);
  const [decision, setDecision] = useState(RULE_DECISIONS[0].key);
  const [value, setValue] = useState("human");
  return (
    <div className="rules__add" role="group" aria-label="New rule">
      <label className="visually-hidden" htmlFor={ids[0]}>
        Kind of task
      </label>
      <select id={ids[0]} className="field__input" value={taskType} onChange={(event) => setTaskType(event.target.value)}>
        {TASK_TYPES.map((type) => (
          <option key={type} value={type}>
            {type}
          </option>
        ))}
      </select>
      <label className="visually-hidden" htmlFor={ids[1]}>
        Decision
      </label>
      <select id={ids[1]} className="field__input" value={decision} onChange={(event) => setDecision(event.target.value)}>
        {RULE_DECISIONS.map((entry) => (
          <option key={entry.key} value={entry.key}>
            {entry.label}
          </option>
        ))}
      </select>
      <label className="visually-hidden" htmlFor={ids[2]}>
        Decided by
      </label>
      <select id={ids[2]} className="field__input" value={value} onChange={(event) => setValue(event.target.value)}>
        {DECIDERS.map((entry) => (
          <option key={entry.value} value={entry.value}>
            {entry.word}
          </option>
        ))}
      </select>
      <Button onClick={() => onAdd({ taskType, decision, value })}>Add</Button>
      <Button variant="quiet" onClick={onCancel}>
        Cancel
      </Button>
    </div>
  );
}

/**
 * The exception rules: each sends one kind of task to a different decider.
 * Add and Remove change the draft; they are saved with the page.
 */
export function PolicyRules({ rules, onChange, describedBy }) {
  const [adding, setAdding] = useState(false);
  const entries = entriesOf(rules);
  return (
    <div className="rules" aria-describedby={describedBy}>
      {entries.length === 0 && !adding ? (
        <span className="rules__none">None. A rule can send one kind of task to a different decider.</span>
      ) : null}
      {entries.length > 0 ? (
        <ul className="rules__list" aria-label="Exception rules">
          {entries.map((rule) => (
            <li key={`${rule.taskType}:${rule.decision}`} className="rules__item">
              <Mono>{rule.taskType}</Mono>
              <span>
                {ruleDecisionLabel(rule.decision)}: {ruleValueWord(rule.decision, rule.value)}
              </span>
              <Button
                variant="quiet"
                inRow
                aria-label={`Remove the ${rule.taskType} rule for ${ruleDecisionLabel(rule.decision).toLowerCase()}`}
                onClick={() => onChange(withoutRule(rules, rule))}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      {adding ? (
        <AddRule
          onAdd={(rule) => {
            onChange(withRule(rules, rule));
            setAdding(false);
          }}
          onCancel={() => setAdding(false)}
        />
      ) : (
        <div>
          <Button onClick={() => setAdding(true)}>Add rule</Button>
        </div>
      )}
    </div>
  );
}
