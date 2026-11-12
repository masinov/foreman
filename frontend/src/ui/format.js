// Formatting shared by pages. Words, not engine jargon (design README, Words).

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatMoney(amount) {
  return money.format(Number(amount) || 0);
}

/** "merge_approval" -> "Merge approval". */
export function humanize(identifier) {
  if (!identifier) return "";
  const words = String(identifier).replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function shortSha(sha) {
  return sha ? String(sha).slice(0, 7) : "";
}

export function plural(count, one, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}

const dayMonth = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const dayMonthYear = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });

/** "11 Nov", with the year when it is not this year's. Empty for no date. */
export function formatDay(timestamp, now = new Date()) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.getFullYear() === now.getFullYear() ? dayMonth.format(date) : dayMonthYear.format(date);
}

/**
 * Split a sprint title at its first colon: "Sprint 55: baseline" gives
 * `["Sprint 55", "baseline"]`. A title without one gives `[title, ""]`.
 */
export function splitTitle(title) {
  const text = String(title ?? "");
  const at = text.indexOf(":");
  if (at <= 0) return [text, ""];
  return [text.slice(0, at).trim(), text.slice(at + 1).trim()];
}

const dayMonthTime = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const dayMonthYearTime = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** "11 Nov, 14:02", with the year when it is not this year's. Empty for no date. */
export function formatDayTime(timestamp, now = new Date()) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.getFullYear() === now.getFullYear() ? dayMonthTime.format(date) : dayMonthYearTime.format(date);
}

/** 28500 -> "28.5K", 1200000 -> "1.2M". */
export function formatTokens(count) {
  const value = Number(count) || 0;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(value);
}

/**
 * A duration in words a person reads at a glance: "7 s", "114.2 s" (to ten
 * minutes, as the test step reports it), then "14 min", then "2 h 5 min".
 * Empty for no value.
 */
export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "";
  const value = Math.max(0, Number(seconds));
  if (value < 600) return `${value.toFixed(1).replace(/\.0$/, "")} s`;
  const minutes = Math.round(value / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}
