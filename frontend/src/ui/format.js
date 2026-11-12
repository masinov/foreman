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
