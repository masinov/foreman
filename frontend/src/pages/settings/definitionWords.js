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

const OUTCOME = {
  "_builtin:run_tests": { success: "the tests pass", failure: "the tests fail" },
  "_builtin:merge": { success: "it merges", conflict: "there is a conflict", failure: "the merge fails" },
  "_builtin:human_gate": { approve: "the person approves", deny: "the person sends it back", steer: "the person steers" },
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

export const GATE_POLICY = {
  merge_approval: "the project's “Approve merges”",
  plan_approval: "the project's “Approve plans”",
};

/** An id from a name: lower case, underscores, starting with a letter. */
export function idFromName(name) {
  const id = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return /^[a-z]/.test(id) ? id.slice(0, 64) : "";
}
