import { humanize } from "../../ui/format";

// The words of the role and workflow editors.

const sentence = (words) => {
  if (words.length < 2) return words.join("");
  return `${words.slice(0, -1).join(", ")} or ${words[words.length - 1]}`;
};

/** A role's tools in a few words. */
export function toolsWords(tools) {
  if (tools.every) return "Every tool";
  if (!tools.chosen.length) return "No tools";
  return tools.chosen.join(", ");
}

/** How a role's run ends, as the engine reads it. */
export function endsWords(role) {
  if (role.ends !== "decides") return "Says it is done";
  const words = sentence(role.decisions);
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Whose a definition is, or nothing for one Foreman ships unchanged. */
export const ORIGIN = {
  shipped: "",
  changed: "changed for this project",
  own: "this project's own",
};

/** The same for the workspace's defaults, which belong to no project. */
export const DEFAULT_ORIGIN = { shipped: "", changed: "changed", own: "added" };

/** The origin words for a scope: a project's id, or null for the workspace. */
export const originWords = (projectId) => (projectId ? ORIGIN : DEFAULT_ORIGIN);

const OUTCOME = {
  "_builtin:run_tests": { success: "the tests pass", failure: "the tests fail" },
  "_builtin:merge": {
    success: "it merges",
    conflict: "there is a conflict",
    failure: "the merge fails",
    updated: "the branch was out of date",
  },
  "_builtin:human_gate": { approve: "the user approves", deny: "the user sends it back", steer: "the user steers" },
  "_builtin:mark_done": { success: "it is marked done" },
  agent: {
    done: "it says it is done",
    approve: "it approves",
    deny: "it denies",
    steer: "it steers",
    escalate: "it escalates",
  },
};

/** One way a step can end, in words, by what does the step. */
export function outcomeWords(role, outcome) {
  return (OUTCOME[role] ?? OUTCOME.agent)[outcome] ?? humanize(outcome).toLowerCase();
}

const SHORT = {
  "_builtin:run_tests": { success: "pass", failure: "fail" },
  "_builtin:merge": { success: "merged", conflict: "conflict", failure: "fails", updated: "out of date" },
  "_builtin:human_gate": { approve: "approved", deny: "sent back", steer: "steered" },
  agent: { done: "done", approve: "approves", deny: "denies", steer: "steers", escalate: "escalates" },
};

/** One way a step can end in a word or two, for the drawing of a workflow. */
export function shortOutcome(role, outcome) {
  return (SHORT[role] ?? SHORT.agent)[outcome] ?? humanize(outcome).toLowerCase();
}

export const GATE_POLICY = {
  merge_approval: "“Approve merges” is a user",
  plan_approval: "“Approve plans” is a user",
};

/** An id from a name: lower case, underscores, starting with a letter. */
export function idFromName(name) {
  const id = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return /^[a-z]/.test(id) ? id.slice(0, 64) : "";
}
