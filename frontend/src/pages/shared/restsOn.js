// The documents a task rests on: written one per line as `path` or
// `path#heading`, shown with the commit the default branch was at when each
// was named. A space before the `#` makes it the separator whatever the path
// holds, so a path with a `#` in it is written `path #heading`, or `path #`.

/** One entry as a line that the server reads back as the same entry. */
export function documentLine(item) {
  if (item.path.includes("#") || /\s#/.test(item.heading ?? "")) return `${item.path} #${item.heading ?? ""}`;
  return item.heading ? `${item.path}#${item.heading}` : item.path;
}

/** The lines of a field for a task's documents. */
export function documentsText(documents) {
  return (documents ?? []).map(documentLine).join("\n");
}

/** The entries a field's lines name: no blank line, each trimmed. */
export function documentsFromText(text) {
  return String(text ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

/** Seven characters of a commit, as the Activity tab shows one. */
export function shortCommit(commit) {
  return String(commit ?? "").slice(0, 7);
}
