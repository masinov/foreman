import { parseDiff } from "./diff";

const DIFF = [
  "diff --git a/foreman/builtins.py b/foreman/builtins.py",
  "index 1111111..2222222 100644",
  "--- a/foreman/builtins.py",
  "+++ b/foreman/builtins.py",
  "@@ -10,3 +10,4 @@ def run_tests():",
  " keep",
  "-old line",
  "+new line",
  "+another",
  "\\ No newline at end of file",
  "",
].join("\n");

describe("parseDiff", () => {
  it("leaves out the file header and numbers lines from the hunk", () => {
    expect(parseDiff(DIFF)).toEqual([
      { kind: "hunk", sign: "", text: "@@ -10,3 +10,4 @@ def run_tests():", oldLine: null, newLine: null },
      { kind: "context", sign: " ", text: "keep", oldLine: 10, newLine: 10 },
      { kind: "del", sign: "−", text: "old line", oldLine: 11, newLine: null },
      { kind: "add", sign: "+", text: "new line", oldLine: null, newLine: 11 },
      { kind: "add", sign: "+", text: "another", oldLine: null, newLine: 12 },
      { kind: "note", sign: "", text: "No newline at end of file", oldLine: null, newLine: null },
    ]);
  });

  it("gives nothing for an empty diff and keeps a line git says instead of a diff", () => {
    expect(parseDiff("")).toEqual([]);
    expect(parseDiff("Binary files a/x.png and b/x.png differ")).toEqual([]);
    expect(parseDiff("something else")).toEqual([
      { kind: "note", sign: "", text: "something else", oldLine: null, newLine: null },
    ]);
  });
});
