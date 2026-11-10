# Foreman: full review and finish plan

- Date: 2026-11-10
- Baseline: `main` at `79d78ab` (2026-09-08), plus the unmerged UI fix branches
  (`fix/dashboard-manager-panel`, `-project-header`, `-working-copy-settings`
  with uncommitted edits).
- Method: direct reading of the spec, mockup, ADRs, status/sprint/backlog and
  the three earlier reviews; four independent code audits (engine core,
  runner/serve/CLI, dashboard backend, frontend), each reading its files in
  full; a live dashboard run against a scratch copy of `.foreman.db` with
  screenshots at 1440, 1024 and 390 px; the Python suite (882 tests, pass,
  90 s). "Reproduced" means a script or request showed the failure against a
  temp repo/DB. "Traced" means the code path was read end to end.

## 1. What the repo is meant to be

Foreman is an autonomous development engine: tasks live in SQLite, each task
walks a declarative TOML workflow (develop, test, review, human gate, merge),
agent CLIs (Claude Code, Codex) do the work as subprocesses in a per-task git
worktree, and a React dashboard plus a CLI let people supervise. The spec
(`engine-design-v3.md`) defines the four core parts (runner, roles, workflow
engine, orchestrator). The goal has since grown past the spec: a resident
service that other systems file work into, with autonomy decided by a policy
matrix, humans only where policy requires, and a chat reachable without a
terminal (`production-readiness-review.md`, ADR-0011 to ADR-0015).

## 2. Where it stands

Built and working: store and migrations (18), roles/workflows, orchestrator
loop, Claude and Codex runners, `foreman serve` with a project lock and command
table, worktree per task, intake endpoint with API tokens, policy matrix with a
triage status, webhook notifications, dashboard, manager chat, 45 CLI commands
with no stubs. Foreman has landed nine of its own tasks ($139 across 85 runs).

Not built: per-task planner step (sprint 54 slice 5), pull-request integration,
facts-based evidence, login and identity, agent sandboxing, CI, packaging that
works outside an editable install.

State of the repository itself:

- Work stopped on 2026-09-08. `main` is 10 commits ahead of `origin/main` and
  unpushed.
- Three UI fix branches are unmerged; the checked-out one has uncommitted
  edits. They merge cleanly with `main` except one trivial conflict in
  `components.jsx` and the committed bundle, which must be rebuilt.
- FOR-12 is `blocked` ("Stopped by dashboard") in the database although its
  branch was merged by hand; its worktree is still live. FOR-11 is a leftover
  live-test task in the intake queue.
- `docs/STATUS.md` is 1,067 lines with duplicate, contradictory "current"
  sections. `/tmp/foreman-ui-refactor` is a stale registered worktree.
- Older code opens a newer-schema database without complaint (the checkout at
  migration 17 served a migration-18 database).

## 3. Findings

Severity is my own ranking after cross-checking the audits. File references
are to `main` unless noted.

### 3.1 Safety of the host and the money (fix before running unattended again)

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| S1 | critical | Any dashboard caller can store `test_command` or `worktree_setup_command` through `PATCH /api/projects/{id}/settings`; the engine later runs it as `bash -lc`. The same call can set triage/plan/merge policy to `auto`. | reproduced (write), traced (execution); `dashboard_service.py:375-423` |
| S2 | critical | Default bind is loopback with no token, bodies are parsed regardless of Content-Type, and there is no Origin or Host check. A web page the operator visits can call the API; with S1 that is remote code execution. | reproduced; `dashboard_backend.py:77-87`, `dashboard_runtime.py:18,175` |
| S3 | high | Worktree prune removes every child directory of `worktree_root`, which is a free-text setting that may be absolute. | reproduced on a scratch directory; `worktrees.py:315-327, 758-763` |
| S4 | high | The cost gate cannot stop spend mid-run (cost only arrives in the final `result` line) and, when it fires, it discards a completed run. Every shipped role sets `max_cost_usd = 1000`. Codex reports cost 0 and has no cost gate. | reproduced with a fake agent; `runner/claude_code.py:192-228, 597-607`, `runner/codex.py:173` |
| S5 | high | A builtin step longer than the 5-minute task lease (tests, setup command) loses the lease after succeeding; recovery resets the task and the developer re-runs without bound. | reproduced with a back-dated lease; `orchestrator.py:1903-1912, 2432` |
| S6 | high | Agents outlive the engine: background children survive a normal finish, SIGHUP/SIGKILL of the engine orphans a full-permission agent, and a process that lingers after `result` turns a finished step into a timeout or a hang. | first and third reproduced; `runner/process.py:75, 217-244, 306` |
| S7 | high | `foreman approve`/`deny` and the dashboard's Approve run the rest of the workflow inline, outside the engine lock and without a task lease. The dashboard version blocks the server's event loop for the whole agent run. Contradicts ADR-0011. | traced; `cli.py:3921-3950`, `dashboard_service.py:1349-1379`, `orchestrator.py:1410-1586` |
| S8 | high | Intake text reaches full-permission agents unfenced and uncapped (a 60 MB description was accepted). Triage gates the developer path but not the manager chat, which sees the title on one click. | traced; size reproduced |
| S9 | high | Every role, reviewers included, and the manager chat run with `bypassPermissions`, the operator's full environment, and the operator's Claude settings. Role `tools.allowed` is parsed and never passed to a runner. | read; `roles/*.toml`, `meta_agent.py:207` |
| S10 | high | `PATCH /api/roles/{id}` rewrites the tracked `roles/*.toml` for all projects with string-only validation and a non-atomic write. One test writes the real file. | traced; `dashboard_service.py:1447-1497` |
| S11 | medium | `judge_base_url` plus `judge_api_key_env` are settable over the API: the engine posts the diff and the named environment variable to a caller-chosen URL. `source.url` accepts `javascript:`. Webhook failure text stores the full target URL in events. `/docs` and `/openapi.json` are served without a token. Tokens are accepted in the query string on every route. | stored values reproduced; execution of the `javascript:` link not tested |

### 3.2 Engine correctness

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| E1 | high | `save_task` is a full-row upsert and the orchestrator holds one stale `Task` for the whole workflow. A task cancelled or edited mid-step is overwritten, then merged and marked done. The fencing token is never checked. | reproduced |
| E2 | high | `signal.blocker` does not stop the workflow: a task that reports a blocker and then prints the completion marker continues to merge. | reproduced |
| E3 | high | Stale-run recovery inside `run_task` force-expires the lease the engine just took and resets the resume point, so every resume after a crash wastes a developer run. | reproduced |
| E4 | high | Any commit on the default branch during a step blocks the running task ("default branch must not be mutated"). With worktrees this no longer detects anything useful and contradicts ADR-0012. | reproduced |
| E5 | high | An exception between creating and completing a run (e.g. `GitError` in merge) leaves a permanent `running` run and an `in_progress` task. | reproduced |
| E6 | medium | A cost limit stored as `0` blocks every task ("$0.00 exceeds limit $0.00"). Unset is fine, but the Settings panel saves the whole payload back, so one Save writes `0`. Gates also exit without releasing the lease. | reproduced; `orchestrator.py:1729` |
| E7 | medium | The resume point is cleared between steps (`workflow_current_step=None`), so a crash in that window restarts the task from the entry step; an approval recorded just before is lost. | traced |
| E8 | medium | Completion evidence parses `git diff --stat` display output: paths with spaces or truncation are wrong, deletions under-counted. The default "proof" is keyword overlap with the developer's own summary, and the test result is not tied to the reviewed commit. | parse reproduced |
| E9 | medium | Infra retries replay the whole prompt with the original session id and lose the aborted attempt's cost; a stale `--resume` id is retried three times and never cleared. Quota detection is a broad regex that can pause the engine for 15 minutes on any error mentioning "quota". | traced |
| E10 | medium | Resident engine: `foreman run` holds the lock but never consumes commands; paused state shown after a restart can be wrong; `run_task` is marked completed when queued in memory; an unexpected exception ends `serve` logging exit 0; `data_version` wakes every idle engine on any commit. | traced |
| E11 | medium | `_ensure_at` force-checks-out a task worktree found on the wrong branch (discarding uncommitted work); the integration worktree never heals after an interrupted merge. | traced |
| E12 | medium | Triage notifications are never queued: intake writes the attention event directly, bypassing the dispatcher. | reproduced (1 event, 0 deliveries) |
| E13 | medium | Task guidance from the dashboard is saved as `human.message` and never read by the engine or the runner. The UI says "sent". | confirmed on `main` (one producer, no consumer) |
| E14 | medium | Autonomous mode: missing `task_started` blocks instead of degrading (contradicts spec §6.2), state is in memory only, the role id `developer` is hard-coded, and the signal's branch name is stored unvalidated. | traced |
| E15 | low | Token counts ignore cache tokens; Codex recounts earlier turns on resume. Test fixtures use usage shapes the real CLI does not emit, so these pass. | reproduced for Claude |

### 3.3 Dashboard backend and API

- Every handler is `async def` doing synchronous SQLite on the event loop; one
  8-second write lock froze all requests, including static pages (reproduced).
- No identity: one shared token, `decided_by="human"`, and `resolved_by` /
  `requested_by` taken from the request body. The policy matrix cannot be
  enforced or audited without a named actor.
- Deletes erase events, runs and gate decisions; a sprint or task can be
  deleted while running; multi-step writes commit per call.
- Task and sprint ids are global slugs written by upsert; intake idempotency is
  check-then-insert on a non-unique index.
- No request models: non-string fields return bare 500s, two error envelopes
  (`error` and `detail`), no versioning, empty OpenAPI schema, no pagination.
- SSE: one connection and a 4 Hz poll per client, sprint scope only, and a
  pruned cursor silently yields nothing forever (reproduced).
- Manager chat subprocess: no kill on disconnect, undrained stderr, no timeout,
  no per-project turn lock, exit code ignored.
- `index.html` is cached at startup, so a rebuild breaks a running server.

### 3.4 Frontend code

- Stale responses overwrite newer state (no request ids or aborts); the project
  and overview pages never refresh; each stream burst resets the activity feed
  and reconnects the stream.
- Edit state is not keyed to its entity: Save in the drawer can write task A's
  fields onto task B. The card-level Deny sends whatever note is in another
  task's drawer, in one click. Gate buttons are never disabled while pending.
- No error boundary; Clear during a manager stream throws inside a state
  updater and blanks the app (traced).
- `App.jsx:980` checks sprint status `"done"`; the backend says `"completed"`,
  so Delete never appears for a completed sprint.
- Three undefined CSS variables (`--surface`, `--surface-hover`,
  `--font-sans`); six classes used with no rule; about 300 dead lines.
- No TypeScript, lint, or formatter; 50 unit tests after merge, none for
  approve/deny, routing, settings save, or any error path.
- After merging `main`: the 4-column grid wraps the Triage and Cancelled
  columns to a second row, and Settings carries three overlapping autonomy
  controls (level radio, autonomous-selection toggle, policy matrix).

### 3.5 UX and visual design (seen in the running app)

The earlier UI design review (2026-09-08) is accurate and almost all of it is
still open. What I saw:

- Overview: the top bar says "No tokens used yet · IDLE" above a project card
  showing 785K tokens and BLOCKED. Two cards on an otherwise empty page.
- Project: completed tasks are struck through and dimmed to near-illegible;
  "1 blocked by the engine" gives no path to the task; destructive Cancel and
  Delete sit permanently on the queue row.
- Sprint: the page title truncates to "Sprint 54: Phase 1 resident e…" while
  the breadcrumb above shows it in full; the activity feed is rows of
  `agent.raw_output` with the event name repeated as the body.
- Task drawer: the key overlaps the title ("FOR-9Add the policy…"); the
  description is a wall of unrendered markdown filling the first screen; the
  full-width red Cancel/Delete outweigh the decision controls; focus stays on
  the card behind; Escape does nothing.
- At 390 px the activity panel covers the board and the header controls
  overlap. At 1024 px card titles wrap to six lines.
- Roles: seven equal cards exposing a free-text permission mode, with stale
  model ids (`claude-opus-4-6`, `claude-sonnet-4-6`) and no link to the
  workflow that uses them.
- Settings: a 2,214 px scrolling drawer in accumulated order, with raw units
  ("ms, 0 = off") and helper text boxed like inputs.
- Typography: 9 to 11 px monospace carries about 70% of text; the tertiary
  grey is 2.5 to 2.9:1 against its backgrounds. The charcoal, gold and serif
  identity is worth keeping; legibility and hierarchy are the problem.
- Accessibility: no dialog semantics or focus trap anywhere, unlabeled close
  buttons, 29 unassociated labels, nested gate buttons unreachable by
  keyboard, no reduced-motion handling.

### 3.6 Code organization

| File | Lines | Problem |
|------|-------|---------|
| `foreman/orchestrator.py` | 4,304 | `run_workflow_from_step` is 723 lines; the block-the-task sequence is hand-written about nine times with inconsistent lease handling |
| `foreman/cli.py` | 3,970 | `build_parser` is 829 lines; handlers mutate rows directly with no events, duplicating the dashboard service |
| `foreman/store.py` | 3,079 | one class over 14 tables; 28 of 40 write sites skip the retrying transaction helper |
| `foreman/dashboard_service.py` | ~2,000 | 56 methods; task creation implemented three times (four with the CLI) |
| `foreman/dashboard_backend.py` | ~810 | one 650-line closure holding every route |
| `frontend/src/components.jsx` | 2,577+ | 17 components; `SprintList` is 511 lines |
| `frontend/src/App.jsx` | 1,185+ | one component with 33 `useState` and the whole sprint view inline |
| `frontend/src/styles.css` | 4,329+ | single file, features appended after the media queries |
| `tests/test_orchestrator.py` | 8,564 | one 4,000-line class, no fixtures, 31 reaches into private state |

Also: statuses, outcomes and event types are bare strings and control flow
depends on prose ("conflict (" in carried output); 26 raw `settings.get`
reads bypass the validated `ProjectSettings`; `foreman/events.py` (319 lines)
is dead; workflow `[[gates]]`, `fallback.action` and the human-gate `steer`
transition are parsed and inert; `_notification_policy` is defined twice in
the orchestrator; `runner_max_cost_usd` is documented and unused.

### 3.7 Delivery, packaging and repo memory

- No CI, no lint, no type check, no formatter, for Python or JavaScript.
- A wheel ships no roles, workflows or templates (they load from the repo
  root), so only the editable install works. Version is defined three times.
- The built bundle is committed with hashed names: every UI branch conflicts
  with every other, and nothing checks it matches the source.
- The manager's operating contract teaches commands that do not exist
  (`foreman task override --model`, `foreman history <project>`).
- Spec gaps: sprint-completion checkpoint tag and note (§6.4) are missing;
  no shipped role or workflow exercises Codex; the architect plan is never
  turned into tasks; nothing fetches or pushes.
- Tests are missing exactly where the reproduced bugs are: no `test_git.py`
  or `test_builtins.py`, 10 tests for the store, none for concurrent writers,
  long builtins, cost gates, CSRF, or approve with a runner present.

## 4. Plan

Principle: make the engine safe and truthful before adding reach, add the
safety net before the big refactors, and redesign the UI once as a system
instead of patching screens. Each phase is one or two sprints of small
slices in the repo's existing style. Estimates assume one person plus agents.

### Phase 0: regain a clean baseline (2 to 3 days, by hand)

1. Commit the working-copy-settings edits; merge the three UI fix branches
   into `main` (keep `PolicyMatrixSection` and the branch's `SettingsPanel`
   signature), rebuild the bundle once, push `main`.
2. Reconcile the database: mark FOR-12 done, remove its worktree and the
   stale `/tmp/foreman-ui-refactor` registration, cancel FOR-11.
3. Cut `docs/STATUS.md` to a one-page current snapshot and move the rest to
   an archive; close sprint 54 and archive it.
4. Add CI (GitHub Actions): Python suite, frontend tests, `ruff`, ESLint with
   the hooks plugin, and a frontend build. Stop committing the bundle; build
   it in CI and at package time.
5. Do not run `foreman serve` or expose the dashboard until Phase 1 lands.

### Phase 1: host and money safety (1 sprint)

- S2: require `application/json`, check Origin/`Sec-Fetch-Site`, add trusted
  hosts, always require a token (generate one at startup for loopback).
- S1, S3, S10, S11: move host-level settings (`test_command`,
  `worktree_setup_command`, `worktree_root`, `context_dir`, `judge_*`, role
  backend and permission mode, repo registration) to an operator-only path;
  prune only directories git reports as this project's worktrees; http(s)-only
  URLs; redact webhook targets.
- S4: pass `--max-budget-usd`, account from `message.usage`, never drop
  `agent.completed`, set real per-role ceilings, record aborted-attempt cost.
- S6: stop reading at the terminal event, always kill the process group,
  handle SIGHUP, set a parent-death signal.
- S5, E3, E6: a `TaskLease` context manager with a timer heartbeat for the
  whole hold; one `block_task()` helper; `0` means off.
- S7: approve/deny record the decision and enqueue an engine command; no
  workflow execution in the CLI or the web process.
- Regression tests for every item, taken from the audit repro scripts.

### Phase 2: engine truthfulness (1 to 2 sprints)

- E1, E2: column-scoped task updates with an expected status, and a status
  re-read before every step.
- E5, E7: try/finally around each step; persist the next step in the same
  write as the transition.
- E4, E11: drop the default-branch assertion in favour of a worktree check;
  self-heal the integration tree; never force-checkout a dirty task tree.
- E8: facts-based evidence (already in the backlog): numstat parsing, test
  result and review tied to the head commit, no numeric score, the word
  "verified" only for checks that ran.
- E9, E10, E12, E14: session-aware retry, structured quota detection, durable
  command lifecycle, triage events through the dispatcher, autonomous-mode
  state persisted.
- E13: deliver guidance to the next agent turn with recorded / delivered /
  acknowledged states, or relabel it as a note.
- Enums for statuses, outcomes and event types with CHECK constraints; one
  `ProjectSettings` object passed down; delete the dead code in 3.6.

### Phase 3: structure (1 to 2 sprints, behaviour-preserving)

Done after Phases 1 and 2 so the refactor moves tested code.

- `foreman/engine/` package (loop, selection, workflow runner, guards, steps,
  signals, leasing, recovery, evidence, output contract).
- `foreman/store/` package: one transaction helper used by every write, one
  repository module per aggregate, `ForemanStore` kept as a facade.
- One task/sprint mutation service used by both CLI and dashboard, emitting
  events and guarding against a running engine.
- `foreman/cli/` package with per-command `register()` and a top-level error
  boundary; `--json` on read commands.
- Dashboard: routers, Pydantic request and response models, one error
  envelope, `/api/v1`, sync handlers on the threadpool, pagination, a
  project-level event stream.
- Roles, workflows and templates as package data; single version source.
- Split `test_orchestrator.py` along the new modules with shared fixtures;
  add `test_git.py`, `test_builtins.py` and store concurrency tests.

### Phase 4: frontend rebuild on a design system (2 sprints)

Start with one design slice agreed before code, as the September review
recommended, and record it as a mockup v7 plus an ADR (the app has already
diverged from v6 on the project view, settings, and policy).

- Foundations: type scale (14 px body, 12 px metadata), spacing scale,
  contrast-passing text tokens, focus-visible, reduced motion; a `Dialog`,
  `SlideOver`, `Field`, `Button` and `Menu` primitive set.
- Data layer: per-scope hooks with stale-request guards, an action hook with
  pending and error state, an error boundary per view, task id in the URL.
- Information architecture: overview that answers "what is running, what
  needs me"; sprint page with a full-width wrapping title and a List/Board
  toggle with Triage and Cancelled as filters; task page with Overview,
  Changes, Checks, Activity tabs and the pending decision at the top;
  settings as a sectioned page with one autonomy model (the policy matrix);
  workflow shown as stages with roles attached.
- Activity as a readable narrative with raw events one level down; rendered
  markdown for descriptions and manager replies.
- Split into `views/`, `features/`, `ui/`, `state/`, `api/` and per-view CSS;
  TypeScript or at least JSDoc types.
- A Playwright acceptance pack for the operator journeys (inspect a running
  task and guide it, review and approve a merge, pause and confirm, recover
  from an engine failure) at desktop and narrow widths.

### Phase 5: finish the product (2 to 3 sprints)

- Planner step per task with a protected acceptance test (slice 5).
- Pull-request integration through `gh`: push, PR with evidence, wait for
  checks and policy approvals, merge through the remote.
- Login and actor identity (decision owed: identity provider), roles
  (viewer, operator, approver, admin), server-derived actor on every
  decision, immutable audit events.
- Agent sandbox: per-role tool allowlists actually passed to the runner,
  read-only reviewers, a scrubbed environment, isolated Claude settings,
  then a container per task.
- Manager chat through the runner with a declared tool set, per-user
  sessions, turn lock, kill on disconnect, cost per turn.
- Notification channel beyond webhooks (decision owed: Slack or email);
  sprint checkpoint tags (spec §6.4); a real Codex role and smoke test, or
  an explicit ADR marking Codex experimental.
- Database out of the repository; migrations as a deploy step with a
  forward-version guard; deployment guide (reverse proxy, TLS, health,
  metrics).

### Decisions (owner, 2026-11-10)

1. Claude drives the work; other agents wait until needed.
2. No identity provider or notification channel is chosen now. Adopters will
   build those; Phase 5 delivers login and notification as pluggable seams.
3. Who executes each slice (by hand or through Foreman, and on which model)
   is decided per slice, and the cost and safety of Foreman runs are recorded.
4. The owner has been developing the dashboard directly, so mockup v6 is
   stale. Phase 4 starts from a design reference built for review before the
   rebuild; its form is still to be agreed.

### Amendment to Phase 0

The bundle stays committed for now, with a CI check that it matches the
source. Removing it from the tree changes how a checkout serves the
dashboard and belongs with the packaging work in Phase 3.
