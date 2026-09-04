const eventTimeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
});

const numberFormatter = new Intl.NumberFormat();
const compactNumberFormatter = new Intl.NumberFormat(undefined, {
  notation: "compact",
  maximumFractionDigits: 1,
});
const currencyFormatter = new Intl.NumberFormat(undefined, {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatCount(value) {
  return numberFormatter.format(value || 0);
}

export function formatCompactCount(value) {
  return compactNumberFormatter.format(value || 0);
}

export function formatTokenCount(value) {
  const tokenCount = value || 0;
  if (tokenCount >= 1000) {
    return `${compactNumberFormatter.format(tokenCount)} tok`;
  }
  return `${numberFormatter.format(tokenCount)} tok`;
}

export function formatCurrency(value) {
  return currencyFormatter.format(value || 0);
}

// Third-party Anthropic-compatible endpoints report $0 cost while token counts
// stay accurate; the engine tracks how many runs that affected so the UI can be
// honest about cost coverage. Returns "" when every run has a known cost.
export function costUnknownNote(totals) {
  const n = totals?.zero_cost_token_runs || 0;
  if (n <= 0) {
    return "";
  }
  return `cost unknown for ${formatCount(n)} run${n === 1 ? "" : "s"}`;
}

export function formatDuration(value) {
  const duration = value || 0;
  if (duration >= 1000) {
    return `${(duration / 1000).toFixed(1)}s`;
  }
  return `${duration}ms`;
}

export function formatEventTime(value) {
  if (!value) {
    return "--:--:--";
  }
  return eventTimeFormatter.format(new Date(value));
}

export function formatDate(value) {
  if (!value) {
    return "—";
  }
  return dateFormatter.format(new Date(value));
}

// Single source of truth for the displayed engine state, so "Running" always
// means an engine resident on the project (holding its engine lock) rather
// than an inferred task-status. Falls back to the legacy `status` field when
// neither `engine` nor `agent_running` is present in the payload.
export function deriveEngineState(project) {
  if (!project) {
    return "idle";
  }
  if (project.engine?.resident) {
    return project.engine.paused ? "blocked" : "running";
  }
  if (project.agent_running) {
    return "running";
  }
  if (project.agent_running === undefined && project.status === "running") {
    // Older payloads without agent_running: keep the inferred status.
    return "running";
  }
  if ((project.task_counts?.blocked || 0) > 0 || project.status === "blocked") {
    return "blocked";
  }
  return "idle";
}

export function formatProjectStatus(status) {
  switch (status) {
    case "running":
      return "Running";
    case "blocked":
      return "Blocked";
    default:
      return "Idle";
  }
}

export function formatSprintStatus(status) {
  if (!status) {
    return "";
  }
  return status.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatTaskStatus(status) {
  switch (status) {
    case "in_progress":
      return "In Progress";
    default:
      return status.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }
}

const SELECTION_MODE_LABELS = {
  directed: "Directed",
  supervised: "Supervised",
  autonomous: "Autonomous",
};

const WORKFLOW_LABELS = {
  development: "Standard workflow",
  development_tiered: "Tiered workflow",
  development_with_architect: "Architect workflow",
};

function titleizeId(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatSelectionMode(mode) {
  return SELECTION_MODE_LABELS[mode] || titleizeId(mode) || "Directed";
}

export function formatWorkflowLabel(workflowId) {
  return WORKFLOW_LABELS[workflowId] || titleizeId(workflowId) || "Standard workflow";
}

export function formatWorkflowCounts(stepVisitCounts) {
  const entries = Object.entries(stepVisitCounts || {});
  if (entries.length === 0) {
    return "none";
  }
  return entries.map(([step, count]) => `${step}=${count}`).join(", ");
}

export function getTaskTypeClass(taskType) {
  // Keys match the backend TASK_TYPES (feature/fix/refactor/docs/spike/chore).
  switch (taskType) {
    case "fix":
      return "tag-fix";
    case "refactor":
      return "tag-refactor";
    case "docs":
      return "tag-docs";
    case "spike":
      return "tag-spike";
    case "chore":
      return "tag-chore";
    default:
      return "tag-feature";
  }
}

// Map any event type to a display category. Every category here has a matching
// `dot-<category>` style and a corresponding activity filter, so no filter is
// ever dead.
export function getEventCategory(eventType) {
  if (eventType.startsWith("human.")) {
    return "human";
  }
  if (
    eventType === "engine.attention_needed" ||
    eventType === "engine.completion_evidence" ||
    eventType === "engine.completion_guard" ||
    eventType.startsWith("gate.") ||
    eventType.includes("review") ||
    eventType.includes("approval")
  ) {
    return "review";
  }
  if (eventType.startsWith("agent.") || eventType.startsWith("signal.")) {
    return "message";
  }
  if (eventType.startsWith("workflow.") || eventType.startsWith("engine.")) {
    return "workflow";
  }
  return "signal";
}

export function eventMatchesFilter(event, filterKey) {
  if (filterKey === "all") {
    return true;
  }
  return getEventCategory(event.event_type) === filterKey;
}

export function formatEventSummary(event) {
  const payload = event.payload || {};
  if (event.event_type === "agent.command") {
    return String(payload.command || "(no command recorded)");
  }
  if (event.event_type === "agent.file_change") {
    return String(payload.path || "(no path recorded)");
  }
  if (event.event_type === "agent.message") {
    return String(payload.text || "(no message text)");
  }
  if (event.event_type === "human.message") {
    return String(payload.text || "(no message text)");
  }
  if (event.event_type === "human.task_edited") {
    const fields = payload.changed_fields ? Object.keys(payload.changed_fields).join(", ") : "fields";
    return `Task edited: ${fields}`;
  }
  if (event.event_type === "engine.attention_needed") {
    return `Attention needed: ${payload.trigger || "decision"}`;
  }
  if (event.event_type === "engine.completion_evidence") {
    const bits = [];
    if (payload.verdict) bits.push(payload.verdict);
    if (payload.proof_status) bits.push(`proof ${payload.proof_status}`);
    if (payload.judged_by) bits.push(`judged by ${payload.judged_by}`);
    return `Evidence: ${bits.join(" · ") || "built"}`;
  }
  if (event.event_type === "workflow.model_selected") {
    const where = payload.step ? ` @ ${payload.step}` : "";
    const why = payload.source ? ` (${payload.source})` : "";
    return `Model: ${payload.model || "default"}${why}${where}`;
  }
  if (event.event_type === "engine.completion_guard") {
    return `Merge guard: ${payload.verdict || payload.error || "blocked"}`;
  }
  if (event.event_type === "gate.cost_exceeded") {
    return `Cost gate: $${payload.actual_usd ?? "?"} ≥ $${payload.limit_usd ?? "?"} (${payload.scope || "task"})`;
  }
  if (event.event_type === "gate.time_exceeded") {
    return "Time limit exceeded";
  }
  if (event.event_type === "workflow.resumed") {
    const details = [];
    if (payload.decision) {
      details.push(`decision=${payload.decision}`);
    }
    if (payload.next_step) {
      details.push(`next=${payload.next_step}`);
    }
    if (payload.note) {
      details.push(`note=${payload.note}`);
    }
    return details.join(" | ") || "Workflow resumed";
  }

  const preferredKeys = [
    "summary",
    "message",
    "note",
    "path",
    "step",
    "decision",
    "next_step",
    "error",
    "session_id",
  ];
  const details = [];
  for (const key of preferredKeys) {
    if (payload[key]) {
      details.push(`${key}=${payload[key]}`);
    }
  }
  return details.join(" | ") || event.event_type;
}

// ── The resident engine ──────────────────────────────────────────────────────

// The engine is a service, not a subprocess the dashboard owns: it is either
// resident on the project (holding its lock and heartbeating), resident but
// paused, or not running at all. `status` is the payload from
// `GET /api/projects/{id}/agent/status`.
export function engineState(status) {
  if (!status || !status.resident) {
    return "stopped";
  }
  return status.paused ? "paused" : "resident";
}

export function formatEngineState(state) {
  switch (state) {
    case "resident":
      return "resident";
    case "paused":
      return "paused";
    default:
      return "not running";
  }
}

// Heartbeat age, rounded to what a person reading a header cares about.
export function formatHeartbeatAge(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) {
    return null;
  }
  if (seconds < 60) {
    return `${Math.max(0, Math.round(seconds))}s ago`;
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m ago`;
  }
  return `${Math.floor(seconds / 3600)}h ago`;
}

// One line for the project header: what the engine is, and how fresh that is.
export function formatEngineSummary(status) {
  const state = engineState(status);
  const label = `Engine: ${formatEngineState(state)}`;
  if (state === "stopped") {
    return label;
  }
  const age = formatHeartbeatAge(status?.heartbeat_age_seconds);
  return age ? `${label} · heartbeat ${age}` : label;
}

// Why a task is blocked. `gate` waits for a human decision; `engine` is the
// engine's dead-letter state and needs a fix or an unblock.
export function formatBlockedKind(kind) {
  switch (kind) {
    case "gate":
      return "human gate";
    case "engine":
      return "engine";
    default:
      return "";
  }
}
