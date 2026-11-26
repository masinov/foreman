# Sprint 65's work, fixed after an independent review

- A merge whose ADR numbering fails is undone, so the integration worktree is
  never left half merged; two new decisions in one branch that name each other
  are both numbered; references are rewritten only in the branch's own files;
  a branch without a decision merges as a plain merge (no pre-commit hook).
- A checkpoint, changelog or copies write that cannot be committed leaves the
  integration worktree clean, and the next write works; a change file that is
  not text is recorded as a checkpoint failure. Foreman refuses to write in a
  dirty integration worktree, and keeps a sprint archive written by hand.
- `foreman changelog` names a finished sprint and waits while one is active.
- The validator asks for the branch's own change file and names a branch that
  edits `CHANGELOG.md`. The sprint context shows the task's key.
- A step moves up its models only after failures of its own work: a run
  stopped by a cost or time limit, a runner that cannot start, a reviewer that
  approved unread, and tests that fail right after the merge step brought the
  branch up to date block or run again without counting. A step with several
  models is still bounded by visits, and a step run again keeps the review's
  findings.
- The shipped prompts no longer apply Foreman's own repository layout to every
  project. MANUAL §9 describes moving up; three ADRs point to the conflicts
  guide.
