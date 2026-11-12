import { humanize } from "../../ui/format";

// The Workflow tab's rows, derived from the workflow the API returns (design
// 08). Nothing here names a step of a particular workflow: who does a step,
// how, when it moves on and where it goes otherwise come from the step's role
// and its transitions, so another definition reads differently.

const BUILTIN = "_builtin:";

export const stepLabel = (id) => humanize(id);

const isBuiltin = (role) => role.startsWith(BUILTIN);
const builtinKind = (role) => role.slice(BUILTIN.length);

const HOW_BUILTIN = {
  run_tests: () => "runs the project's test command",
  merge: ({ defaultBranch }) => `merges the task branch into ${defaultBranch || "the default branch"}`,
  mark_done: () => "marks the task done",
};

// What a step's outcome is called in a sentence, by what does the step.
const OUTCOMES = {
  agent: {
    done: "it reports the work done",
    approve: "it approves",
    deny: "it denies",
    steer: "it steers",
    blocked: "it is blocked",
    error: "it fails to run",
  },
  run_tests: { success: "the tests pass", failure: "the tests fail" },
  merge: { success: "the merge succeeds", conflict: "the merge conflicts", failure: "the merge fails" },
  human_gate: { approve: "approved", deny: "denied", steer: "sent back" },
  default: { success: "it succeeds", failure: "it fails", done: "it is done" },
};

function outcomeWords(role, outcome) {
  const kind = isBuiltin(role) ? builtinKind(role) : "agent";
  return OUTCOMES[kind]?.[outcome] ?? OUTCOMES.default[outcome] ?? `its outcome is ${outcome}`;
}

function sentence(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function joinOr(items) {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} or ${items[items.length - 1]}`;
}

/** Who does a step, as `{ text, quiet }`. */
function doneBy(step, rolesById, decidedBy) {
  if (!isBuiltin(step.role)) return rolesById[step.role]?.name ?? humanize(step.role);
  if (builtinKind(step.role) === "human_gate") {
    return step.policy ? (decidedBy[step.policy] ?? "A person") : "A person";
  }
  return "Engine";
}

/** How a step is done, as `{ text, model }`. */
function how(step, rolesById, { defaultBranch }) {
  if (!isBuiltin(step.role)) {
    const role = rolesById[step.role];
    return { text: "agent, ", model: role?.model || null, fallback: "project default model" };
  }
  const kind = builtinKind(step.role);
  if (kind === "human_gate") {
    return { text: step.policy ? "this project's Who decides setting" : "always waits for a person" };
  }
  const describe = HOW_BUILTIN[kind];
  return { text: describe ? describe({ defaultBranch }) : "a built-in step" };
}

/**
 * The rows of the steps table. `decidedBy` maps a gate's policy (`merge_approval`)
 * to who decides it now, as the page's words ("A person" or "Foreman").
 *
 * A transition to a later step is how a step moves on; one to the same or an
 * earlier step is where it goes otherwise.
 */
export function stepRows(workflow, { decidedBy = {}, defaultBranch = "" } = {}) {
  const rolesById = Object.fromEntries(workflow.roles.map((role) => [role.id, role]));
  const order = workflow.steps.map((step) => step.id);
  return workflow.steps.map((step, index) => {
    const outgoing = workflow.transitions.filter((t) => t.from === step.id && t.outcome);
    const forward = outgoing.filter((t) => order.indexOf(t.to) > index);
    const back = outgoing.filter((t) => order.indexOf(t.to) <= index);

    const next = order[index + 1];
    const movesOn = forward.length
      ? joinOr(forward.map((t) => outcomeWords(step.role, t.outcome))) +
        (forward.some((t) => t.to !== next) ? ` (goes to ${joinOr([...new Set(forward.map((t) => stepLabel(t.to)))])})` : "")
      : null;

    const byTarget = new Map();
    for (const transition of back) {
      const key = `${transition.to}:${transition.carry_output}`;
      const entry = byTarget.get(key) ?? { to: transition.to, carry: transition.carry_output, outcomes: [] };
      entry.outcomes.push(outcomeWords(step.role, transition.outcome));
      byTarget.set(key, entry);
    }
    const otherwise = [...byTarget.values()].map(
      (entry) =>
        `${sentence(`if ${joinOr(entry.outcomes)}`)}: back to ${stepLabel(entry.to)}${entry.carry ? ", with its output" : ""}`,
    );

    return {
      id: step.id,
      label: stepLabel(step.id),
      doneBy: doneBy(step, rolesById, decidedBy),
      how: how(step, rolesById, { defaultBranch }),
      movesOn,
      final: outgoing.length === 0,
      otherwise,
    };
  });
}

/** Where a requirement comes from, by its kind (ADR-0018). */
export const REQUIREMENT_SOURCES = {
  fact: { kind: "Fact", source: "measured by the engine" },
  claim: { kind: "Claim", source: "reported by the reviewing agent" },
};
