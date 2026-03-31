const eventTimeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
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

export function formatTaskStatus(status) {
  switch (status) {
    case "in_progress":
      return "In Progress";
    default:
      return status.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }
}

export function formatWorkflowCounts(stepVisitCounts) {
  const entries = Object.entries(stepVisitCounts || {});
  if (entries.length === 0) {
    return "none";
  }
  return entries.map(([step, count]) => `${step}=${count}`).join(", ");
}

export function getTaskTypeClass(taskType) {
  switch (taskType) {
    case "bug":
      return "tag-bug";
    case "refactor":
      return "tag-refactor";
    case "chore":
      return "tag-chore";
    default:
      return "tag-feature";
  }
}

export function getEventCategory(eventType) {
  if (eventType.startsWith("agent.command")) {
    return "command";
  }
  if (eventType.startsWith("agent.file")) {
    return "file";
  }
  if (eventType === "human.message") {
    return "human";
  }
  if (eventType.startsWith("workflow.") || eventType.startsWith("engine.")) {
    return "workflow";
  }
  if (eventType.includes("review") || eventType.includes("approval")) {
    return "review";
  }
  if (eventType.startsWith("agent.message")) {
    return "message";
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
