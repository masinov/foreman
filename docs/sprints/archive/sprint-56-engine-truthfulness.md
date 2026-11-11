# Sprint 56 — engine truthfulness (archived)

- **Opened:** 2026-11-11, from Phase 2 of
  `docs/reviews/2026-11-10-full-review-and-finish-plan.md`
- **Status:** done (closed 2026-11-11)
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
| 1 | Safe task writes: the engine updates only the columns it owns, never touches a cancelled task, re-reads the task before every step, and stops when it finds the task cancelled or blocked; `signal.blocker` stops the workflow | done | Claude, by hand | `fix/safe-task-writes`: `update_task_engine_state`, `_save_task`, `_adopt_operator_changes`, 3 tests |
| 2 | Crash-safe steps: the next step is written in the same update that leaves the current one, so a crash between steps resumes there; an engine error inside a step settles its run as failed instead of leaving it `running`; built-in steps record their real duration | done | Claude, by hand | `fix/crash-safe-steps`: orchestrator, 2 tests |
| 3 | Default-branch check: a task is blocked only when its own commits are on the default branch before the merge step, not whenever that branch moves | done | Claude, by hand | `fix/default-branch-check`: `git.task_commits_on_default_branch`, orchestrator, ADR-0012 amendment, 3 tests |
| 3b | The integration worktree heals an interrupted merge; a task tree on the wrong branch is never force-checked-out while dirty | done | Claude, by hand | `fix/worktree-self-heal`: `worktrees.py`, 3 tests |
| 4 | Test step truth: real duration, a result line as the run detail, the head commit recorded on `engine.test_run` (using it as evidence is slice 8) | done | Foreman (Sonnet 5.5 developer and reviewer; about $0.72 notional, half of it a repeat visit caused by the old default-branch check) | `foreman/builtins.py`, `tests/test_builtins.py` (7 tests) |
| 5 | Triage attention events go through the notification dispatcher | done | Foreman (Sonnet 5.5; about $0.56 notional, same repeat visit) | `dashboard_service.py`, 4 tests in `tests/test_intake.py` |
| 6 | Manager operating contract lists commands that exist | done | Foreman (Haiku 5.5 developer and reviewer; about $0.03 notional) | contract text, drift test |
| 7 | Completed sprints can be deleted from the sprint page (the page compared the status with `"done"`; the status is `"completed"`) | done | Claude, by hand (a frontend task needs `npm ci` and a bundle rebuild in the worktree, which the engine's test step does not cover) | `fix/completed-sprint-delete`: `App.jsx`, 1 test, rebuilt bundle |
| 8 | Facts-based evidence: no numeric score or verdict ladder; test and review facts tied to the head commit; criteria reported as not checked unless a judge model ran | done | Claude, by hand (touches the model, builder, merge guard, events, prompts and the task drawer together) | `refactor/facts-based-evidence`: ADR-0018, `models.py`, `orchestrator.py`, `judge.py`, `builtins.py`, drawer panel; 11 backend and 4 frontend tests replace 17 score tests |
| 9 | Guidance reaches the agent: a note is recorded, put into the next agent step's prompt, and marked delivered with the role and step. No "acknowledged" state: nothing in an agent's output can prove it, so none is claimed | done | Claude, by hand | `feat/guidance-delivery`: `foreman/guidance.py`, orchestrator, service, drawer section; 4 backend and 2 frontend tests |
| 10a | Infrastructure retries continue the interrupted session and keep its cost; an unknown session id is dropped; quota stops are decided by the rate-limit notice, not by any error mentioning "quota" | done | Claude, by hand | `fix/retry-and-quota`: `runner/base.py`, `runner/claude_code.py`, orchestrator; 7 tests |
| 10b | Resident engine: `foreman run` answers engine commands; a pause survives a restart; `run_task` is completed when its task has run; an unexpected exception ends `serve` non-zero; idle engines do not wake on unrelated commits | done | Claude, by hand | `fix/resident-engine-commands`: `serve.py`, `cli.py`, `store.project_activity_token`; 11 tests |
| 10c | Autonomous mode: tasks get a branch and worktree (they ran in the operator's checkout); a missing `task_started` degrades instead of blocking; no in-memory state; no hard-coded role id; reported type and branch validated | done | Claude, by hand | `fix/autonomous-mode`: orchestrator, `context.py`, ADR-0012 amendment; `tests/test_autonomous_mode.py` (6 tests, the first for this mode) |
| 11 | The database refuses statuses and types outside the models' vocabulary (migration 20, triggers); one typed settings accessor replaces the scattered raw reads; unused code removed | done | Claude, by hand | `refactor/status-constraints`: `migrations.py`, `settings.settings_of`, orchestrator, builtins, worktrees, context; 4 guard tests. Not done here: Python `Enum` classes for statuses (the `Literal` types and tuples stay); the judge still takes a mapping |

### Carried from sprint 55

Findings from the FOR-13 run: the worktree setup command now installs the
`dev` extra so agents can run ruff (project setting, changed 2026-11-11);
role model ids were refreshed (reviewers on `claude-sonnet-5-5`, triage on
`claude-haiku-5-5`, architect and frontier reviewer on `claude-opus-5-5`);
the test-step findings are slice 4.

### Slice 1 notes

- A task's status is not guarded by an expected-value check on every write.
  The rule that matters is narrower and absolute: a cancelled row is never
  written by the engine, and a step never starts for a task that is
  cancelled or blocked. Edits to wording, criteria, priority, dependencies
  and overrides are picked up between steps.
- `foreman task block` on a running task still does not interrupt the agent
  mid-step; the workflow stops when that step ends. Interrupting is the
  engine command `stop-task`.
- The fencing token on leases is still not checked on writes. With one
  engine per project (ADR-0011) nothing can exploit that today; it returns
  with parallel workers.

### Lesson from opening this sprint

The role model refresh was merged after running only `test_roles.py`, and
broke an assertion in `test_cli.py` on `main` for 40 minutes while Foreman
tasks were starting from it. Fixed in `5d5528f`. The whole suite runs
before every merge, including docs-and-config ones.

### Slice 3 notes

Done out of order because it stopped the sprint: the old assertion blocked
FOR-14 when the test hotfix reached `main` during its develop step, and
would block anything in flight at every later merge. The developer's work
was intact on its branch each time; only the resume point was thrown away.

### Slice 2 notes

- Recovery itself is unchanged: a task found `in_progress` with a step
  resumes at that step, one found without a step is reset to `todo`. What
  changed is that the second state no longer occurs between steps, so the
  common crash costs one step, not the task.
- A stale `running` agent run is still reset by `_recover_stale_running_runs`
  to the entry step with visit counts cleared. Resuming that step in place
  (the session id is kept on the run) is left for slice 10.

### Close-out (2026-11-11)

All slices landed on `main`; 1064 Python tests and 60 frontend tests pass;
CI is green on every merge of the sprint.

What Foreman built and what it cost (notional; models run on a
subscription):

| Task | Developer / reviewer | Time to the gate | Notional cost | Result |
|---|---|---|---|---|
| Manager contract lists real commands | Haiku 5.5 / Haiku 5.5 | 5 min | $0.03 | correct first time |
| Test step reports duration, result, commit | Sonnet 5.5 / Sonnet 5.5 | 9 min | $0.72 | correct; one develop visit repeated because of the old default-branch check |
| Triage events through the notifier | Sonnet 5.5 / Sonnet 5.5 | 6 min | $0.56 | correct; same repeat |

Observations carried forward:

- A tightly briefed, self-contained change with a test to write is safe to
  delegate, and Haiku was enough for the smallest one. More than 97% of the
  tokens in every run were cache reads.
- The Sonnet re-reviews took about 7 seconds and under 1,000 output tokens.
  They approved correct work; whether they would catch incorrect work is
  untested. A planted-defect review test is owed before review is relied on
  without a person reading the diff.
- Frontend work cannot go through Foreman yet: a task worktree has no
  `node_modules`, and the test step runs only the Python suite.
- Everything that changed the workflow loop, the store's write path, the
  evidence model or the engine's command handling was done by hand. Each
  touched several modules at once and two of them (the default-branch check
  and autonomous mode) were found broken only while being worked on.
- Defects found by writing the first test for something: autonomous tasks
  had no worktree (slice 10c); a dashboard fixture used a task type that
  does not exist (slice 11).
