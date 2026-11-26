# A code map for agents, surveyed in depth

- Date: owner, 2026-11-25
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**A code map for agents, surveyed in depth (owner, 2026-11-25).** What
each step is given about the repository so that it starts in the right
place without reading its way through (ADR-0041 sets the three layers:
project, task, step). The owner likes the idea of a generated map of the
code, as Aider's "repo map" does (symbols from tree-sitter, ranked by how
much they are referenced). It likely pays more as a codebase grows. "Worth
a deep research on tools like this so 1: we can borrow from what already
exists ... and 2: we design a truly robust system that saves time AND
tokens. But we can save that for later, since nothing depends on it
strictly."
- **To survey:** Aider's repo map, code indexes (ctags, tree-sitter tags,
  LSP, Sourcegraph's SCIP), the search agents already do, and published
  comparisons of indexes against plain search.
- **Measure first:** reads before the first edit and tokens per step,
  which Foreman can count from the tool calls it records (ADR-0041), so
  the survey can be judged on this repository and Assay.
