# Current Sprint

## Sprint 56 — engine truthfulness

- **Opened:** 2026-11-11, from Phase 2 of
  `docs/reviews/2026-11-10-full-review-and-finish-plan.md`
- **Status:** in_progress
- **Method:** Claude drives. Cross-cutting changes to the workflow loop and
  the store are done by hand. Self-contained items are filed as tasks and
  run through Foreman with the developer on Sonnet, to keep measuring where
  delegation is safe and cheaper. Foreman tasks are told not to edit
  `CHANGELOG.md` (every branch touching the same lines conflicts at merge);
  the entry is added when the task lands. Merge approval stays a human
  gate: Claude reviews each diff and the owner approves, or authorises
  Claude to.

### Goal

What the engine records is what happened, and what an operator does takes
effect: a cancelled task is not merged, a blocker stops the workflow, a
crash costs one step, a triage task reaches its notification, and evidence
states facts.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 1 | Safe task writes: the engine updates the columns it owns with an expected status and re-reads the task before every step, so an operator's cancel, block or edit made mid-step is not overwritten; `signal.blocker` stops the workflow | todo | Claude, by hand | store, orchestrator, tests |
| 2 | Crash-safe steps: try/finally settles every run; the next step is persisted in the same write as the transition; recovery resumes at that step | todo | Claude, by hand | orchestrator, tests |
| 3 | Worktree check in place of the default-branch assertion; the integration worktree heals an interrupted merge; a task tree on the wrong branch is never force-checked-out while dirty | todo | Claude, by hand | orchestrator, worktrees, git, ADR-0012 amendment |
| 4 | Test step truth: real duration, a result line as the run detail, test result tied to the head commit | todo | Foreman | builtins, tests |
| 5 | Triage attention events go through the notification dispatcher | todo | Foreman | service, notifications, tests |
| 6 | Manager operating contract lists commands that exist | todo | Foreman | meta_agent, tests |
| 7 | Completed sprints can be deleted from the sprint page (`"done"` vs `"completed"`) | todo | Foreman | frontend, test |
| 8 | Facts-based evidence: no numeric score or verdict ladder; test, review and criteria facts tied to the head commit; "verified" only for checks that ran | todo | to decide | orchestrator, judge, frontend, ADR |
| 9 | Guidance reaches the agent: recorded, delivered and acknowledged states, or relabelled as a note | todo | to decide | service, orchestrator, runner, frontend |
| 10 | Session-aware retry, structured quota detection, durable engine commands, autonomous-mode state persisted | todo | to decide | runner, serve, orchestrator |
| 11 | Enums with CHECK constraints for statuses and outcomes; one settings object passed down; dead code removed | todo | to decide | models, migrations, settings |

### Carried from sprint 55

Findings from the FOR-13 run: the worktree setup command now installs the
`dev` extra so agents can run ruff (project setting, changed 2026-11-11);
role model ids were refreshed (reviewers on `claude-sonnet-5-5`, triage on
`claude-haiku-5-5`, architect and frontier reviewer on `claude-opus-5-5`);
the test-step findings are slice 4.
