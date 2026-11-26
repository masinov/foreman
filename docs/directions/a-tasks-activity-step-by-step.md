# A task's Activity, step by step

- Date: owner, 2026-11-22
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

From a review of every step of ASS-10 and ASS-16 as a user, and a second
review that saw only screenshots. The mockup the owner chose:
https://claude.ai/artifact/5XgyCnzgX7QyeVFCJMj2we (one kind of line, the
step's facts beside it, the prompt as the first line).

- **Done, the step panel (`feat/task-step-panel`).**
- **Done, the table (`feat/task-steps-table`):**
  - only the task's own steps;
  - "attempt 2", "Committed" and "Approved by setting";
  - the commit on Test, Review and Merge rows.

- **Done, the test count (`feat/test-report-count`, sprint 62 slice 1,
  ADR-0035):** read from the JUnit XML the test command writes into
  `FOREMAN_TEST_REPORT_DIR`. A step's records are saved as they happen, so
  the test step's start is when the tests started.
- **Done (sprint 62 slice 4, by Foreman, ADR-0038), facts that need the repository:** the files a step changed with
  their added and removed lines, and for a merge what it brought in, where
  main was before, and whether the branch was kept. Also "Session:
  continued from attempt 1", which today is only in the agent's command
  line.
- **Done, engine fixes found on the way:** records about a sprint or the
  engine are stored as the sprint's or the project's own, not pinned to a
  task (ADR-0037, sprint 62 slice 3). After it (owner, 2026-11-24): a
  task's Activity lists every record the engine kept on it, so it shows at
  least what its sprint's does; the worktree clean-ups are the project's;
  a sprint's Activity does not list the sprint's own records.
