import { humanize } from "../../ui/format";

// The words of the settings pages (design 08, 10): plain, no engine jargon.

/** Who decides: the two answers every decision has. */
export const DECIDERS = [
  { value: "human", word: "A person" },
  { value: "auto", word: "Foreman" },
];

export const decider = (value) => DECIDERS.find((entry) => entry.value === value)?.word ?? humanize(value);

/** The decisions an exception rule can send elsewhere, in the order the page lists them. */
export const RULE_DECISIONS = [
  { key: "triage", label: "Accept filed work" },
  { key: "plan_approval", label: "Approve plans" },
  { key: "merge_approval", label: "Approve merges" },
];

const NOTIFICATION_WORDS = {
  none: "Never",
  attention: "When something needs me",
  all: "About everything",
};

export const NOTIFICATIONS = Object.entries(NOTIFICATION_WORDS).map(([value, word]) => ({ value, word }));

/** The word for one value of one decision, for a rule's line. */
export function ruleValueWord(decision, value) {
  return decision === "notification" ? (NOTIFICATION_WORDS[value] ?? humanize(value)) : decider(value);
}

export function ruleDecisionLabel(decision) {
  return (
    RULE_DECISIONS.find((entry) => entry.key === decision)?.label ??
    (decision === "notification" ? "Tell me" : humanize(decision))
  );
}

/** The host-level settings the page shows, with what each is called and says when empty. */
const MACHINE_ROWS = {
  worktree_root: { label: "Working copies", empty: "The default, inside the project's .foreman folder" },
  worktree_setup_command: { label: "Set up a working copy with", empty: "Nothing" },
  worktree_link_paths: { label: "Linked into each working copy", empty: "Nothing" },
  context_dir: { label: "Context folder", empty: "The default" },
  judge_base_url: { label: "Criteria judge address", empty: "Not set" },
  judge_api_key_env: { label: "Criteria judge key variable", empty: "Not set" },
};

/**
 * The rows of "This machine": every host-level setting the API names except
 * the test command (shown under Tests), as `{ key, label, value }` where
 * `value` is null when nothing is set. Unknown keys are shown by name.
 */
export function machineRows(hostLevel, effective) {
  const known = Object.keys(MACHINE_ROWS);
  const keys = (hostLevel ?? []).filter((key) => key !== "test_command");
  keys.sort((a, b) => {
    const rank = (key) => (known.includes(key) ? known.indexOf(key) : known.length);
    return rank(a) - rank(b);
  });
  return keys.map((key) => {
    const raw = effective?.[key];
    const value = Array.isArray(raw) ? raw.join(", ") : raw;
    return {
      key,
      label: MACHINE_ROWS[key]?.label ?? humanize(key),
      value: value ? String(value) : null,
      empty: MACHINE_ROWS[key]?.empty ?? "Not set",
    };
  });
}
