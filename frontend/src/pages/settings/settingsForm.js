// The General settings form as data: how each setting is read into a draft
// and written back (design 10). Pure functions, so a page only holds state.
//
// A draft holds one string per setting (a choice's value, or what is typed),
// except `policy_rules`, which is an object. Only the settings whose draft
// differs from what was read are sent.

const WHOLE = /^\d+$/;

function parseNumber(text) {
  const trimmed = String(text).trim();
  if (!trimmed || Number.isNaN(Number(trimmed))) return null;
  return Number(trimmed);
}

// An amount of minutes typed by a person, as the stored unit. Empty is "none".
function minutes(factor) {
  return {
    read: (value) => (value > 0 ? String(value / factor) : ""),
    write: (text) => {
      if (!String(text).trim()) return { value: 0 };
      const number = parseNumber(text);
      if (number === null) return { error: "Enter a number of minutes." };
      return { value: Math.round(number * factor) };
    },
  };
}

function whole({ required = false } = {}) {
  return {
    read: (value) => (value === null || value === undefined ? "" : String(value)),
    write: (text, { empty }) => {
      const trimmed = String(text).trim();
      if (!trimmed) return required ? { error: "Enter a whole number." } : { value: empty };
      if (!WHOLE.test(trimmed)) return { error: "Enter a whole number." };
      return { value: Number(trimmed) };
    },
  };
}

const choice = { read: (value) => String(value ?? ""), write: (text) => ({ value: text }) };
const text = { read: (value) => String(value ?? ""), write: (value) => ({ value: String(value).trim() }) };

const money = {
  read: (value) => (value > 0 ? String(value) : ""),
  write: (value) => {
    if (!String(value).trim()) return { value: 0 };
    const number = parseNumber(value);
    return number === null ? { error: "Enter an amount in dollars." } : { value: number };
  },
};

const days = {
  read: (value) => (value === null || value === undefined ? "" : String(value)),
  write: (value) => {
    if (!String(value).trim()) return { value: null };
    return WHOLE.test(String(value).trim()) ? { value: Number(value) } : { error: "Enter a number of days." };
  },
};

const rules = {
  read: (value) => structuredClone(value ?? {}),
  write: (value) => ({ value }),
};

/** How every editable setting is read and written. Keys are the API's. */
export const CODECS = {
  triage: choice,
  plan_approval: choice,
  merge_approval: choice,
  policy_rules: rules,
  task_selection_mode: choice,
  max_autonomous_tasks: { ...whole({ required: true }) },
  cost_limit_per_task_usd: money,
  cost_limit_per_sprint_usd: money,
  time_limit_per_task_ms: minutes(60000),
  max_step_visits: { ...whole({ required: true }) },
  max_live_worktrees: { ...whole(), empty: 0 },
  default_model: text,
  meta_agent_model: text,
  test_timeout_seconds: minutes(60),
  notification: choice,
  event_retention_days: days,
  run_retention_days: days,
  prompt_retention_days: days,
};

export const EDITABLE = Object.keys(CODECS);

/** What each editable setting says when it is read from the effective values. */
export function toDraft(effective) {
  return Object.fromEntries(EDITABLE.map((key) => [key, CODECS[key].read(effective?.[key])]));
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** The keys whose draft differs from what was read. */
export function changedKeys(initial, draft) {
  return EDITABLE.filter((key) => !same(initial[key], draft[key]));
}

/**
 * The settings to send: only what changed, written as the API stores it.
 * Returns `{ settings }`, or `{ errors }` keyed by setting for what could not
 * be written (nothing is sent then).
 */
export function changesOf(initial, draft) {
  const settings = {};
  const errors = {};
  for (const key of changedKeys(initial, draft)) {
    const codec = CODECS[key];
    const written = codec.write(draft[key], { empty: codec.empty ?? null });
    if (written.error) errors[key] = written.error;
    else settings[key] = written.value;
  }
  return Object.keys(errors).length ? { errors } : { settings };
}
