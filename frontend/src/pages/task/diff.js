// A unified diff from git, split into the lines the Changes tab shows.

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/;
const FILE_HEADER = /^(diff --git |index |--- |\+\+\+ |new file mode|deleted file mode|old mode|new mode|similarity index|rename from|rename to|copy from|copy to|Binary files )/;

/**
 * `[{ kind, sign, text, oldLine, newLine }]`, where `kind` is `hunk`, `add`,
 * `del`, `context` or `note` and `sign` is the leading `+`, `−` or a space.
 * Git's file header lines are left out: the page names the file already.
 * Line numbers count from each hunk header.
 */
export function parseDiff(text) {
  const rows = [];
  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;
  for (const line of String(text ?? "").split("\n")) {
    const hunk = HUNK.exec(line);
    if (hunk) {
      oldLine = Number(hunk[1]);
      newLine = Number(hunk[2]);
      inHunk = true;
      rows.push({ kind: "hunk", sign: "", text: line, oldLine: null, newLine: null });
      continue;
    }
    if (!inHunk) {
      if (FILE_HEADER.test(line) || line === "") continue;
      rows.push({ kind: "note", sign: "", text: line, oldLine: null, newLine: null });
      continue;
    }
    if (line.startsWith("\\")) {
      rows.push({ kind: "note", sign: "", text: line.slice(1).trim(), oldLine: null, newLine: null });
    } else if (line.startsWith("+")) {
      rows.push({ kind: "add", sign: "+", text: line.slice(1), oldLine: null, newLine: newLine });
      newLine += 1;
    } else if (line.startsWith("-")) {
      rows.push({ kind: "del", sign: "−", text: line.slice(1), oldLine: oldLine, newLine: null });
      oldLine += 1;
    } else if (line.startsWith(" ")) {
      rows.push({ kind: "context", sign: " ", text: line.slice(1), oldLine: oldLine, newLine: newLine });
      oldLine += 1;
      newLine += 1;
    } else if (FILE_HEADER.test(line)) {
      // The next file's header in a combined diff.
      inHunk = false;
    }
  }
  return rows;
}
