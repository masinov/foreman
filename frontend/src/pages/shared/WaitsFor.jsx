import React from "react";

import { Disclosure } from "../../ui/Disclosure";
import { Mono } from "../../ui/Mono";
import { plural } from "../../ui/format";

/**
 * The tasks a task waits for: a closed line that opens a list to tick.
 * `candidates` are the tasks that can be ticked, `value` a Set of the ids
 * that are, `onChange` gets the new Set. Renders nothing with no candidates.
 */
export function WaitsFor({ candidates, value, onChange }) {
  if (!candidates.length) return null;

  function toggle(id) {
    const next = new Set(value);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  }

  return (
    <Disclosure summary={value.size ? `Waits for ${plural(value.size, "task")}` : "Make it wait for other tasks"}>
      <p className="field__hint">It does not start until every task ticked here is done.</p>
      <ul className="choice-list">
        {candidates.map((task) => (
          <li key={task.id}>
            <label className="choice-list__label">
              <input type="checkbox" className="checkbox" checked={value.has(task.id)} onChange={() => toggle(task.id)} />
              {task.task_key ? <Mono quiet>{task.task_key}</Mono> : null}
              <span>{task.title}</span>
            </label>
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}
