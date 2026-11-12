# Changelog

All notable changes to this repository should be documented here.

The repo is still pre-release, so entries currently track milestone and repo
memory changes rather than versioned product releases.

## [Unreleased]

### Sprint 58 — frontend rebuild

- **feat, a proposed sprint order is in Needs you** (`feat/task-b1e9a964d00e`):
  `GET /needs-you` carries pending decision gates as `settle_order` items,
  the workspace counts them, and the workspace and project pages show them
  with Accept and Reject, so `/dashboard/legacy` is no longer needed to
  settle one.

- **built frontend bundle out of git** (`chore/frontend-bundle-out-of-git`),
  by owner decision: `foreman/dashboard_frontend_dist` is ignored and no
  longer committed. `foreman dashboard` builds it when it is missing or older
  than the frontend source (`FOREMAN_DASHBOARD_NO_BUILD=1` turns that off),
  serves a rebuilt bundle without a restart, and the API starts without it
  (the shell route answers 503 with how to build). CI builds it in the Python
  job and drops the freshness check. A release must run
  `npm --prefix frontend run build` before `python -m build`. Five sprint 58
  merges had been sent back for conflicts in the committed bundle.

- **fix, a review sees the whole change** (`fix/review-sees-the-whole-change`):
  the second sprint 58 task (1,310 changed lines) was approved by the
  reviewer in 7 seconds; the diff in its prompt is capped (16,000 characters
  by default) and nothing told it the rest was missing. Reviewer prompts now
  say that a truncated diff means reading the changed files in full first,
  and the built frontend bundle is marked `-diff` in `.gitattributes` so it
  does not use up the cap.

- **fix, a step cannot leave work in the background**
  (`fix/agent-steps-wait-in-foreground`): the first sprint 58 task was
  blocked with its work done. The agent's test run outlived Claude Code's
  120 s command timeout, was moved to the background, and the agent ended
  its turn to wait for it, which ends a headless step. The Claude Code
  runner now starts every step with background commands off and a 20 minute
  default command timeout (`HEADLESS_STEP_ENV`; a role's `[agent.env]`
  overrides it), and the developer prompts say a step ends when the message
  ends.

- **design reference** (`docs/dashboard-design-v7`): `docs/design/dashboard-v7/`
  is the UI reference (17 screens and a README with the rules), replacing
  `docs/mockups/foreman-mockup-v6.html`, which is kept as history. ADR-0020
  records the design and how the frontend is built (layout, routes, data
  hooks, the temporary `/dashboard/legacy` seam). `AGENTS.md`, `CLAUDE.md`,
  `README.md`, `docs/ARCHITECTURE.md` and `docs/TESTING.md` point to it.
  Sprint 57 is archived; its undecided slice 9 is in the backlog.

### Sprint 57 — structure

- **slice 2c, workflow runner** (`refactor/workflow-runner`): the step loop
  and its phases are `foreman/engine/workflow_runner.py` (`WorkflowRunner`).
  `foreman/orchestrator.py` is 832 lines (4574 at the start of the sprint)
  and holds the project pass, running one task under a lease, and resuming
  a human gate. No behaviour change.
- **slice 8, tests along the modules** (`test/split-orchestrator-tests`):
  `tests/test_orchestrator.py` (8279 lines) is 13 files named for what they
  cover, on shared fixtures in `tests/engine_support.py`; 31 copies of the
  same six fixture methods are gone. The same 1110 tests run. New:
  `tests/test_git.py` (13 tests of the git helpers, which had none of their
  own) and `tests/test_store_concurrency.py` (5 tests with a connection per
  thread: a lease raced for by eight engines has one winner, concurrent
  event writes all land once, tasks created at once get distinct keys).
- **slice 7, package data and one version** (`chore/package-data`): the
  role and workflow definitions and the scaffold template moved from the
  repository root into the package (`foreman/data/roles/`,
  `foreman/data/workflows/`, `foreman/data/templates/`) and are listed as
  package data. A Foreman installed from a wheel had none of them and could
  not load a role; it only worked from a source checkout. The version is
  stated once, in `foreman/__init__.py`; `pyproject.toml` and the API read
  it from there.
- **slice 6b, API handlers, typed bodies, project stream**
  (`refactor/api-handlers-off-loop`):
  - the 37 non-streaming handlers run on the thread pool; they blocked the
    event loop on every database call, so one slow request stalled the
    event streams of everyone connected;
  - write routes with a fixed shape take typed bodies
    (`foreman/dashboard/schemas.py`). A field of the wrong type is refused
    by name; `{"title": null}` used to create a task titled "None";
  - `GET /api/v1/projects/{id}/stream`: one event stream for a whole
    project across its sprints, resumable with `Last-Event-ID`. The loop it
    shares with the sprint stream is `foreman/dashboard/streaming.py`.
- **slice 6a, routed and versioned API** (`refactor/dashboard-api`,
  ADR-0019): the 40 API routes moved out of the application factory into
  `foreman/dashboard/routers/` (projects, intake, sprints, meta, gates,
  engine, worktrees, tasks, roles). The API is served under `/api/v1`, with
  `/api` kept as an alias; the frontend uses `/api/v1`. Every error,
  including unknown routes, bad parameters, authentication failures and
  bugs, is `{"error": "<sentence>", "code": "<kind>"}`; an unhandled
  exception no longer leaks as a bare 500.
- **slice 5, CLI package** (`refactor/cli-package`): `foreman/cli.py` (3915
  lines) is the package `foreman/cli/`: `parser` (the parser and `main`),
  `common`, and a module per command group (`projects`, `sprints`, `tasks`,
  `gates`, `monitor`, `engine`, `tokens`, `notify`, `worktree`, `catalog`,
  `db`). Each command adds itself with a `register_<command>` function; the
  829-line parser builder is 26 calls. New for an operator: `--json` on
  `projects`, `sprint list`, `task list` and `engine status`; and one error
  boundary, so a failure is one `foreman:` line with exit 1, a bug says it
  is one and exits 70 (`FOREMAN_DEBUG=1` for the traceback).
- **slice 4, one mutation service** (`refactor/mutation-service`):
  `foreman/mutations.py` is the single implementation of the changes a
  person makes to tasks (accept, block, unblock, cancel, delete) and sprints
  (lifecycle, delete). The CLI and the dashboard both call it. What changed
  for an operator:
  - every task change records an audit event (`human.task_accepted`,
    `_blocked`, `_unblocked`, `_cancelled`) with who made it and from which
    surface; CLI changes left no trace before;
  - a task an engine is running cannot be deleted, and a sprint holding one
    cannot be deleted (only cancel was guarded);
  - the dashboard refuses to complete a sprint that still has unresolved
    tasks and names them, as `foreman sprint complete` always did; cancel the
    sprint to abandon what is left;
  - `foreman sprint complete` on a planned sprint is refused (activate it
    first), following the same transition table as the dashboard.
- **slice 3, store package** (`refactor/store-package`): `foreman/store.py`
  (3213 lines) is the package `foreman/store/`: `base` (connection, write
  helper, migrations), `rows` (row to model), and a part per aggregate
  (`projects`, `sprints`, `tasks`, `runs`, `events`, `gates`, `meta`,
  `leases`, `commands`, `tokens`, `notifications`). `ForemanStore` is those
  parts together and its interface is unchanged. One behaviour change: the
  20 writes that opened their own transaction (leases, sprints, projects,
  gates, manager sessions, pruning, task delete) failed immediately when
  another process held the database lock; they now retry like the rest.
- **slice 2b, engine package, third cut** (`refactor/engine-collaborators`):
  the orchestrator now composes collaborators from `foreman/engine/`:
  `TaskWrites`, `Retention`, `SprintFlow`, `Recovery`, `TaskSelector`,
  `SignalHandler`, `AgentStepRunner`, `PromptBuilder`, `TaskWorktrees`. The
  750-line step loop is a 170-line loop over named phases
  (`_task_worktree_problem`, `_limit_reached`, `_run_human_gate_step`,
  `_run_builtin_step`, `_run_agent_step`, `_record_step_completed`,
  `_follow_transition`), with one `_block_at_step` where seven copies of
  "record a blocked run and park the task" used to be. No behaviour change;
  `orchestrator.py` is 1883 lines, from 4574 at the start of the sprint.
- **slice 2a, engine package, second cut**
  (`refactor/engine-leases-and-records`): `TaskLeases` (`engine/leasing.py`)
  owns lease tokens and heartbeats; `RunRecords` (`engine/records.py`) is
  the engine's only writer of runs and events; branch refresh and conflict
  guidance are functions in `engine/branch_sync.py`; prompt-context and gate
  helpers are in `engine/prompts.py` and `engine/gates.py`. No behaviour
  change; `orchestrator.py` is 3144 lines.
- **slice 1, engine package, first cut** (`refactor/engine-package`): the
  separable parts of `foreman/orchestrator.py` are now modules of
  `foreman/engine/`: `errors`, `results`, `limits`, `model_selection`,
  `output_contract` and `evidence` (`EvidenceBuilder`). No behaviour change;
  `orchestrator.py` went from 4574 to 3754 lines. `builtins.py` no longer
  constructs an orchestrator to build evidence.

### Sprint 56 — engine truthfulness

- **slice 11, vocabulary and settings** (`refactor/status-constraints`):
  - migration 20: the database refuses a task status, task type, task
    complexity, sprint status, run status or project autonomy level that is
    not in `foreman/models.py`, through triggers (SQLite cannot add a CHECK
    to an existing table without rebuilding it). A test fixture that used
    the task type `bug` was the first thing it caught;
  - engine code reads settings through one typed, validated accessor,
    `settings.settings_of(project)`; the per-module helpers that each
    repeated a default and a type coercion are gone. `runner_max_cost_usd`
    now defaults to 0 (the role's ceiling applies), which is what the code
    did and the manual said; the model said 1000;
  - removed code nothing called: the typed-events module
    (`foreman/events.py`, never adopted by the engine) and six unused
    functions.
- **slice 10c, autonomous mode** (`fix/autonomous-mode`):
  - an autonomous task now gets its own branch and worktree like any other.
    It had neither, so the agent ran in the operator's checkout, committed
    to the branch checked out there, and the merge step failed with "Task
    branch is not set" (found by the first tests written for this mode);
  - an agent that never sends `signal.task_started` no longer blocks the
    task: the gap is recorded once and review goes ahead, as spec §6.2
    describes;
  - nothing about the mode is kept in memory, so a restart mid-task changes
    nothing; the check no longer names the `developer` role, it applies to
    any role allowed to send the signal;
  - a task type or branch reported by the agent is checked before it is
    stored; one that is not acceptable is refused with `signal.rejected`.
- **slice 10b, resident engine** (`fix/resident-engine-commands`):
  - a one-shot `foreman run` answers engine commands while it holds the
    project: `pause`, `shutdown` and `stop_task` stop its step (they sat
    unread before), and it refuses a `run_task` with the reason;
  - a pause outlives the engine that applied it: a restarted engine starts
    paused, so the state every screen reads is the state the engine is in;
  - a `run_task` stays `acknowledged` until its task has run and is then
    completed with what happened (it was `completed` on being queued); one
    accepted by an engine that then stopped is run by the next engine;
  - an unexpected exception ends `foreman serve` with `stop_reason: crashed`
    and exit code 1 (the log said exit 0);
  - an idle engine wakes for a change to its own project's settings,
    sprints, tasks, commands or queued notifications, not for every commit
    by any process.
- **slice 10a, retries and quota** (`fix/retry-and-quota`): after an
  infrastructure failure the retry continues the session the failed attempt
  opened (it replayed the whole prompt before); a session id the backend
  does not know is dropped and the step starts a fresh session instead of
  failing three times on it; what a failed attempt had already cost is kept
  on the run. A usage-quota stop is decided by the CLI's rate-limit notice
  when there is one, and otherwise only by the CLI's own phrases, so an
  error that merely mentions "quota" or "rate limit" no longer pauses the
  engine.
- **slice 9, guidance delivery** (`feat/guidance-delivery`): a guidance
  note written for a task now reaches an agent. The engine appends every
  note no agent has received to the prompt of the task's next agent step and
  records `human.message_delivered` with the notes, role and step. The API
  answers `recorded` (it said `sent` while nothing read the note), says when
  a finished task means no agent will read it, and the task drawer lists
  each note as waiting or read.
- **slice 8, facts-based evidence** (`refactor/facts-based-evidence`,
  ADR-0018): completion evidence no longer has a score or a verdict. It
  records whether the tests passed and on which commit, what each reviewer
  decided and on which commit (new `engine.review_recorded` event), and what
  a judge model said about each criterion when one is configured. Tests or an
  approval that are about an older commit than the branch head fail the
  proof. The keyword-overlap criteria check is deleted: without a judge the
  criteria are reported as not checked. The task drawer shows these as rows
  of fact, and the reviewer prompts are reworded to match.
- **slice 3b, worktree self-heal** (`fix/worktree-self-heal`): the
  integration worktree aborts a merge a killed engine left half-done instead
  of refusing every later merge; a task tree found on the wrong branch is
  moved back only when it has no changes to tracked files, and is otherwise
  reported and left untouched (the checkout was forced before, which
  discarded such changes).
- **slices 4, 5, 6, built through Foreman** (approved at the merge gate and
  merged by the engine):
  - the test step's run detail opens with a result line ("Tests passed in
    114.2s (exit 0)."), and `engine.test_run` carries `duration_seconds`
    and the `head_sha` the tests ran against;
  - a new item waiting for triage is handed to the notification dispatcher,
    so the webhook channel hears about it under the same policy as other
    attention events;
  - the manager's operating contract names only commands and flags the CLI
    has, with a test that fails when the two drift apart.

- **slice 7** (`fix/completed-sprint-delete`): the sprint page offers
  Delete on a completed sprint; it compared the status with `"done"`, which
  no sprint ever has.
- **slice 2, crash-safe steps** (`fix/crash-safe-steps`): a workflow
  transition records the next step in the same write, so an engine that
  dies between two steps resumes at the next one instead of restarting the
  task; an unexpected error inside a step marks its run failed instead of
  leaving it `running` (which refused the task until the stale-run window
  passed); built-in steps record how long they took.
- **slice 3, default-branch check** (`fix/default-branch-check`): a task is
  no longer blocked because the default branch moved while it ran (an
  operator commit, another task's merge). It is blocked only when its own
  commits are on the default branch before the merge step. ADR-0012 amended.
- **slice 1, safe task writes** (`fix/safe-task-writes`): the engine no
  longer replaces a task's whole row. `update_task_engine_state` writes
  workflow state only and never a cancelled row; before every step the
  engine re-reads the task, adopts an operator's edits, and stops if the
  task was cancelled or blocked. A task cancelled while a step runs stays
  cancelled, its open run is settled, and it is not merged. A blocker
  reported by the agent stops the workflow instead of being overtaken by the
  completion marker.
- opened sprint 56 from Phase 2 of the 2026-11-10 finish plan; refreshed
  shipped role model ids (reviewers `claude-sonnet-5-5`, triage
  `claude-haiku-5-5`, architect and frontier reviewer `claude-opus-5-5`)

### Sprint 55 — baseline and host safety

- **completion-evidence diff stats from numstat**
  (`fix/task-parse-completion-evidence-diff-stats-from-git-numstat`): the
  evidence builder reads changed files and added/deleted totals from
  `git diff --numstat -z` instead of parsing `git diff --stat`. Paths with
  spaces and long paths are reported whole, binary files are listed as
  changed, renames are reported under the new path, and deletion totals are
  exact. The returned tuple shape is unchanged; its integer is now the
  changed-file count.
- **slice 6, gate decisions through the engine**
  (`fix/gate-decisions-through-engine`): `foreman approve`, `foreman deny`
  and the dashboard's Approve and Deny record the decision and leave the
  task at the step it leads to; the engine continues it. They no longer run
  workflow steps in the CLI or the web process, outside the engine lock.
  The CLI prints whether an engine is resident and the command to continue;
  the dashboard shows a notice when none is. A task paused at a human gate
  now releases its lease instead of making the engine wait it out.
  ADR-0011 amended.
- **slice 5, task lease lifecycle** (`fix/task-lease-lifecycle`): new
  `foreman/task_lease.py` renews a task's lease on a timer for the whole of
  `run_task`, so a built-in step longer than the lease (tests, worktree
  setup) no longer loses it and re-runs the developer; stale-run recovery
  inside `run_task` re-acquires the lease instead of expiring the one just
  taken; a task parked `blocked` by a loop, cost or time gate or a failed
  guard releases its lease.
- **token split** (`feat/token-usage-breakdown`): runs store input, output,
  cache-read and cache-creation tokens separately (migration 19,
  `TokenUsage`); `run_totals` and `task_run_totals` sum them; the API adds
  `token_usage` to runs and totals; `foreman cost` prints a `Token split`
  line and `foreman history` adds `in=`/`out=`/`cache_read=`/`cache_write=`;
  the task drawer, run history and sprint footer show the split.
- **slice 4, engine death** (`fix/runner-parent-death`): SIGHUP (a closed
  terminal or dropped SSH session) is handled as a shutdown like SIGTERM;
  on Linux every agent the engine starts is sent SIGTERM if the engine dies
  with no handler running (SIGKILL, out-of-memory kill, crash), so a
  full-permission agent no longer keeps working unobserved.
- **slice 3, cost control** (`fix/runner-cost-control`): the per-run cost
  ceiling is handed to Claude Code as `--max-budget-usd` so spend stops
  while the agent works; a run whose result has arrived is never reported
  as killed; a budget stop is recorded as a cost kill with its real cost;
  shipped roles carry ceilings of $2 to $30 in place of $1,000;
  `runner_max_cost_usd` now lowers a role's ceiling (it was documented and
  unused); a task or sprint cost limit of 0 means off instead of blocking
  every task; the runner stops reading at the result line, bounds the wait
  for exit, and kills process-group leftovers after a normal finish.
- **slice 2, host-level settings** (`fix/host-level-settings`): the dashboard
  API refuses changes to `test_command`, `worktree_setup_command`,
  `worktree_root`, `worktree_link_paths`, `context_dir`, `judge_base_url`
  and `judge_api_key_env` (403 naming the key and the `foreman config`
  command) and to a role's `backend` and `permission_mode`; the Settings and
  Roles screens show them read-only. Worktree removal deletes only git
  worktrees of the project's repository and never the root; other
  directories are listed as not owned and kept. Role files are validated
  before they replace the old one. Intake source URLs must be http(s).
  ADR-0017.
- CI: install setuptools before the editable install (first run failed in
  `tests/test_cli.py` on a fresh 3.12 virtualenv).
- **slice 1, browser-origin defence** (`fix/dashboard-browser-origin-defence`):
  new `foreman/dashboard_guard.py`; every `/api` request except intake is
  refused when its `Host` is not a trusted name (token-less binds), when its
  `Origin` is not the dashboard's own or an allowlisted one, or when the
  browser labels a write cross-site; request bodies must be declared
  `application/json`; `?token=` works on GET only; `/docs`, `/redoc` and
  `/openapi.json` are off. Closes the cross-site and DNS-rebinding routes to
  the settings API reproduced in the 2026-11-10 review. ADR-0016.
- **slice 0, baseline** (`chore/phase0-baseline`): merged the three operator
  UI fixes with the policy matrix and triage UI and rebuilt the bundle; added
  CI (`.github/workflows/ci.yml`: Python suite on 3.10 and 3.12, ruff,
  repo-memory validation, frontend tests and build, bundle freshness) and a
  ruff baseline with a `dev` extra; restored six completion-evidence tests
  that a lost class header had shadowed; replaced the 1,067-line
  `docs/STATUS.md` with a current snapshot (history preserved under
  `docs/checkpoints/`); added the 2026-09-08 reviews and the 2026-11-10 full
  review and finish plan; closed and archived sprint 54

### Sprint 54 — Phase 1 resident engine and intake

- opened sprint 54 from Phase 1 of the production readiness review with the
  live-run protocol (slices executed through `foreman run foreman`)
- **slice 1, resident engine**
  (`feat/task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock`):
  new `foreman serve <project-id> [--poll-seconds N] [--once]` keeps the engine
  resident — each pass runs `run_project` once, and an idle pass waits on
  `PRAGMA data_version` or the poll interval instead of exiting, so work queued
  by another process is picked up without a person pressing Run. New
  `foreman/engine_lock.py` enforces one engine per project through a lease with
  `resource_type="engine"` (no migration: the `leases` table already supports
  arbitrary resource types), renewed from a daemon timer thread on its own
  store connection; `foreman run` takes the same lock, so neither can start
  while the other is resident. A task whose execution raises is blocked with
  the error as its `blocked_reason` plus an `engine.attention_needed` event and
  the service continues after a backoff (5 s, doubling, capped at 5 minutes,
  reset after a clean pass); SIGTERM settles the active run as `killed`, leaves
  the task resumable, releases the lock, and exits 0. New `foreman/logs.py`
  emits JSON lines on stderr — `serve` never prints, and the orchestrator
  mirrors every persisted event to the same logger, levelled by family
  (`foreman.logs.event_log_level`): the narrative at INFO, the agent output
  firehose at DEBUG. Retention pruning and crash recovery are gated behind
  `run_project(maintenance=...)` so idle wakes stay cheap. Recorded as
  ADR-0011; `foreman run --json-logs` opts into the same log format.
- **slice 2, the engine command table and the `foreman engine` CLI**
  (`feat/task-add-the-engine-command-table-and-foreman-engine-cli`): migration
  15 adds `engine_commands` (`pause`, `resume`, `run_task`, `stop_task`,
  `shutdown`; `pending` → `acknowledged` → `completed`/`rejected`) with an
  index on `(project_id, status, requested_at)` and `ON DELETE CASCADE` from
  both `projects` and `tasks`. `ForemanStore` gains `enqueue_engine_command`,
  `list_engine_commands`, `next_pending_engine_command`,
  `mark_engine_command`, and `get_engine_lock`, the last returning a
  token-free `EngineLockView` (holder, acquired, heartbeat, expiry) so
  operator surfaces can see who holds a project without the secret that would
  let them release it. The resident engine drains pending commands before
  every pass and supplies the orchestrator with a new `command_poll`
  callback, called before every workflow step and on every `agent.tick`, so a
  `pause` reaches an agent that has been quiet for twenty minutes: the agent
  process group is terminated and the run settled as `killed` through the
  existing `_abandon_run` path (`gate_type="command"`). `pause` leaves the
  task resumable and the engine resident, idle, and still heartbeating its
  lock; `stop_task` marks the task `blocked` with `blocked_reason`
  "Stopped by \<requester\>"; `shutdown` releases the lock and exits 0. Every
  command records `engine.command_applied` or `engine.command_rejected`, and a
  starting engine rejects pending `pause`/`stop_task`/`shutdown` with
  `result_detail="no engine was resident"` while honouring pending `resume`
  and `run_task`. New `foreman engine
  status|pause|resume|shutdown|run-task|stop-task`, with `--by` defaulting to
  the OS user name and the command id printed. ADR-0011 amended to record the
  command table as the only control channel to a resident engine. The
  dashboard is untouched and moves onto the table in the next slice. Merging
  main's quota pause in also made the engine's long waits (a failure backoff,
  a quota reset) command-aware: they end early when a command arrives, so a
  `shutdown` is answered in seconds rather than after a six-hour quota wait,
  and a paused engine narrates `serve.paused` once at INFO and then at DEBUG
  the way an idle one does.
- **slice 3, the dashboard on the resident engine + dead-letter reporting**
  (`feat/task-rewire-the-dashboard-onto-the-resident-engine-and-report-dead-letter-tasks`):
  the dashboard no longer manages processes. `_RUNNING_PROCS` and its
  process-handle helpers are gone from `foreman/dashboard_service.py`; Run
  enqueues `resume` (plus `run_task` for a task-scoped start), Pause enqueues
  `pause` and changes no task status, and a task Stop enqueues `stop_task` for
  the engine to act on. New `GET /api/projects/{id}/agent/status` reports
  `resident`, `holder_id`, `heartbeat_age_seconds`, `paused`, `current_task`,
  and the last ten commands; new `GET /api/projects/{id}/engine/commands`
  lists the log. With no engine resident there is nobody to send `resume` to,
  so the service spawns a detached `foreman serve <project> --db <path>`
  (stdout and stderr appended to `.foreman/serve.log`) through an injectable
  `ServeSpawner` — the single-machine bootstrap, and the only process the
  dashboard starts. New `foreman/engine_control.py` holds the read-side
  derivations the CLI and the dashboard share, so the two surfaces cannot
  answer "is an engine resident", "is it paused", or "why is this task
  blocked" differently from the same database. Dead-letter reporting: a
  derived `blocked_kind` of `gate` (parked at a `_builtin:human_gate` step) or
  `engine` (loop limit, unhandled outcome, cost or time gate, branch
  violation, failure isolation, `stop_task`) on task payloads, `foreman task
  show`, and `foreman board`, with `blocked_gate`/`blocked_engine` counts on
  project summaries and `foreman status` — derived from the workflow
  definition, no schema change and no new task status. `foreman task unblock`
  now refuses only the `gate` kind, so an engine dead letter with a persisted
  resume step can be cleared instead of being mistaken for a gate. The
  frontend header shows "Engine: resident / paused / not running" with the
  heartbeat age, its stop control says Pause, and blocked cards carry the
  kind. ADR-0002 amended: the dashboard controls the engine only through the
  command table.
- `fix/keep-session-on-kill`: a run that is killed or interrupted (shutdown,
  lease loss, an engine `pause`/`stop_task`) keeps the backend session id
  announced by `agent.session`, and the native step records that id as soon
  as it is announced, so the resumed visit continues the conversation instead
  of re-reading the repository.
- **slice 4, one git worktree per task**
  (`feat/task-give-every-task-its-own-git-worktree`): the engine no longer
  changes what is checked out in the operator's repository. New
  `foreman/worktrees.py` owns a `WorktreeManager` per project: task worktrees
  live under `<repo>/.foreman/worktrees/<task-key-or-id>/` (relocatable with
  the new `worktree_root` setting), are created on a task's first develop
  visit from the existing task branch or a new one cut from the default
  branch, reused on every later visit, and removed by `_builtin:mark_done`, by
  `foreman task cancel`, by the dashboard's cancel and delete, and by
  `foreman worktree prune`. Migration 16 adds the nullable
  `tasks.worktree_path` so the CLI, the dashboard, and a restarted engine
  agree on where a paused task's work lives. Native role steps run with
  `working_dir` = the task's tree; `_builtin:run_tests` runs the test command
  there (the `engine.test_started`/`engine.test_run` events carry
  `working_dir`); the context projection is mirrored into the worktree's own
  `.foreman/` so the agent finds `context.md` where it works; the branch
  invariants check the worktree's branch; and the refresh-before-develop and
  conflict-recovery merges happen there. `run_task` and `resume_human_gate` no
  longer check a branch out in `project.repo_path` or restore one afterwards.
  `_builtin:merge` runs its `--no-ff` merge in a shared
  `<worktree_root>/_integration` tree pinned to the default branch — the
  operator's checkout only sees the ref move — and now also refuses a dirty
  task worktree, since uncommitted work there is not on the branch and would
  be silently dropped; both dirty-tree guards judge the task's own tree and
  never the operator's checkout. The "default branch did not move during a step"
  invariant stays. Worktrees survive human gates, quota pauses, review rounds,
  and engine restarts. New `foreman worktree list|prune <project>`; `foreman
  task show` and `foreman history` print the path and the dashboard task
  drawer renders it. `run_project` preflights once before leasing any task, so
  a repository whose worktree root is not ignored, or a git older than
  `git worktree`, fails with one clear message instead of mid-step. New
  `worktree_link_paths` setting symlinks ignored local tooling (`venv`,
  `node_modules`) from the operator's checkout into every new worktree, since
  a worktree is a clean checkout and the project's `test_command` needs it.
  `tests/test_cli.py` no longer reinstalls the package when the virtualenv
  points at a different checkout, and runs every CLI subprocess as
  `python -m foreman` with `PYTHONPATH` pinned to the checkout under test, so
  a suite run inside a worktree cannot repoint the operator's virtualenv.
  ADR-0012.
- **slice 4b, bounded worktree disk use and a per-worktree environment**
  (`chore/task-c68378a4e541`): the two follow-ups ADR-0012 left open. New
  `max_live_worktrees` (default 4, `0` disables) caps how many task worktrees
  exist at once; `worktrees.enforce_worktree_limit` runs from the engine
  immediately *before* it creates a tree, so the cap bounds peak disk use
  rather than its steady state. It never touches the integration tree or the
  tree of the task about to run, reclaims done/cancelled/unclaimed trees
  first and then the least recently used (measured by each tree's own git
  index mtime), and **never reclaims a tree with uncommitted changes** — that
  work is not on the branch, so removing it would destroy exactly the paused
  state worktrees exist to preserve. A reclaimed task keeps its branch and
  workflow position, has `worktree_path` cleared, and gets a fresh tree on its
  next visit; a project whose candidates are all dirty stays above its cap and
  records `engine.worktree_limit_exceeded` (with `engine.worktrees_reclaimed`
  and `engine.worktree_reclaim_failed` for the other outcomes). New
  `worktree_setup_command` (and `worktree_setup_timeout_seconds`, default
  1800) runs once inside each newly created tree with
  `FOREMAN_WORKTREE_PATH`/`FOREMAN_REPO_PATH`/`FOREMAN_WORKTREE_BRANCH`/`FOREMAN_DEFAULT_BRANCH`
  exported, so a tree builds its *own* environment instead of borrowing the
  operator's through `worktree_link_paths`; a marker in the tree's git admin
  directory (never in the tree, which would dirty it and block the merge)
  makes it run once and reprovision when the command changes. This repository
  now sets it to build a per-tree venv and editable install, and
  `worktree_link_paths` is empty — a task's `./venv/bin/python -m unittest
  discover -s tests` runs on that tree's own interpreter. The dashboard
  project screen gains the live tree count against the cap, the worktree root,
  and a Prune worktrees control, backed by new
  `GET /api/projects/{id}/worktrees` and
  `POST /api/projects/{id}/worktrees/prune`. ADR-0012 amended.
- **slice 5, the intake endpoint and API tokens**
  (`feat/task-add-the-intake-endpoint-and-api-tokens-v2`): Foreman can now be
  handed work by a system rather than a person. New
  `POST /api/projects/{id}/intake` files one task from a JSON body (`title`
  required; `description`, `acceptance_criteria`, `task_type` defaulting to
  `fix`, `priority`, `complexity`, `source`, `sprint_id`) and answers **201**
  with `created: true` for new work or **200** with `created: false` for a
  repeat, returning the task exactly as `GET /api/tasks/{id}` serializes it.
  Migration 17 adds `api_tokens` — named, per-project, revocable credentials
  with a scope list, cascading from `projects`, unique on `token_hash` — plus
  `tasks.source_system` / `source_ref` / `source_url` / `reporter` indexed on
  `(project_id, source_system, source_ref)`. New `foreman/api_tokens.py` is the
  only module that mints or hashes a secret (`fmn_` + 32 random bytes,
  SHA-256); the secret is returned once by `create_api_token`, printed once by
  `foreman token create <project> --name NAME`, and reaches no row, log line,
  or event payload. `foreman token list|revoke` complete the surface; revoke
  writes a timestamp rather than deleting, so old tasks' `created_by` still
  resolves. **Intake is idempotent on the caller's own key** `(project,
  source.system, source.external_ref)` — the caller is what retries, so a
  re-delivered webhook is one task, returned unchanged. **The intake queue is
  a sprint**: work filed without `sprint_id` lands in `<project>-intake`
  ("Intake queue"), created on first use, `active` when no sprint is running
  and `planned` when one is, reactivated once that sprint finishes — sprints
  stay the unit of grouping and a continuous queue is a sprint that never
  completes, so no consumer needs a code path for a sprintless task. The two
  credentials are kept apart in both directions by the token middleware: the
  shared dashboard token is refused on intake, and an `fmn_` token is refused
  with 403 on every other `/api` route whether or not a dashboard token is
  configured. Auth outcomes are now service errors (`DashboardAuthError` 401,
  `DashboardPermissionError` 403) so the transport maps status codes instead
  of deciding them. Tasks carry `source` in their serialization and the task
  drawer shows the system, the reference (linked when a `url` was sent), and
  the reporter; filing emits `intake.task_created` on a synthetic `intake` run
  carrying the source and the token's id and name. Recorded as ADR-0013 and
  documented in MANUAL §25. (The task specified migration 16 and ADR-0012;
  both were taken by slice 4, so this landed as 17 and ADR-0013.)
- **slice 6, the policy matrix**
  (`feat/task-add-the-policy-matrix-triage-plan-merge-and-notification-decisions-v2`):
  autonomy is now a policy, not a mode. New `foreman/policy.py` owns four
  decisions — `triage` (`auto`/`human`, default `human`), `plan_approval`
  (default `human`), `merge_approval` (default `auto`), and `notification`
  (`none`/`attention`/`all`, default `attention`) — each resolved from three
  layers, most specific first: the task's `executor_overrides` (`policy`, or
  the older gate-only `gates`), a rule for the task's type from the new
  `policy_rules` setting (`{"<task_type>": {"<decision>": "<value>"}}`), then
  the project default setting, else the built-in. Nothing else resolves a
  policy: `ForemanOrchestrator._gate_policy_decision` delegates to the matrix
  and `DashboardService.intake_task` asks it for the arriving status.
  **Resolution reports its source**, and every task's first step writes one
  `policy.resolved` event carrying all four `(value, source)` pairs
  (`task_override`, `task_type_rule` plus the type, `project_default`,
  `built_in_default`), so the audit trail says *why* a person was or was not
  asked; a new `ForemanStore.has_event` keeps it to one per task across
  resumes. Settings are **strict on write** (`ProjectSettings` refuses an
  unknown task type, decision, or value, so `foreman config --set
  policy_rules=…` fails at the typo) and **lenient on read** (a stored value
  the matrix does not recognize is dropped for the built-in default rather than
  stopping a run). New task status **`triage`**: work filed through intake
  under a `human` triage policy lands there instead of `todo`, where
  `select_next_task` never sees it, and raises one `engine.attention_needed`
  turn with trigger `triage`; `foreman task accept <task-id>` and
  `POST /api/tasks/{id}/accept` move it to `todo`, and `task cancel` works from
  it. New `GET /api/projects/{id}/policy` returns the defaults, their sources,
  and the rules, with `?task_id=` adding one task's resolution; the task
  payload carries its resolved `policy`; `foreman task override` takes
  `--triage` and `--notification` alongside the unchanged `--gate`; and
  `foreman config` prints the matrix. The dashboard grows a `triage` board
  column (shown only when work is waiting there) with an **Accept** action, the
  resolved policy in the task drawer, and a defaults-plus-rules editor in
  settings. `notification` is stamped as `notify` on
  `engine.attention_needed` and `workflow.paused`, providing the durable
  decision consumed by the following delivery slice. **No migration** —
  `status` is a text column and
  settings are JSON. Existing projects are unaffected: the two gate settings
  keep their names, defaults, and `executor_overrides.gates` shape,
  `workflow.gate_auto_approved` and the gate decision records keep their shape,
  `triage` only touches intake tasks, and `notification` only adds a payload
  field. Recorded as ADR-0014 and documented in MANUAL §14. (The task specified
  ADR-0013, which slice 5 had already taken, so this landed as ADR-0014.)
- **slice 7, durable notification delivery** (`feat/task-d5da554de317`,
  FOR-12): migration 18 adds project-scoped webhook destinations and a durable
  delivery outbox. The orchestrator turns policy-stamped attention, human-gate,
  and completion events into one idempotent row per enabled destination without
  performing network work. `foreman serve` drains bounded batches between
  passes and `foreman run` drains once before returning. Webhook POSTs use a
  versioned, self-contained JSON payload, optional static headers, and optional
  HMAC-SHA256 signing whose secret is read from a named environment variable
  rather than stored. Failures retry with exponential backoff capped at 30
  minutes; the fifth failed attempt leaves a diagnostic row and emits
  `notification.failed` without changing the source task. New `foreman notify
  add|list|remove|test|deliveries` manages and diagnoses the channel. The
  dispatcher and worker are failure-isolated from task execution. Recorded as
  ADR-0015 and covered by `tests/test_notifications.py`.
- `fix/cancelled-dependency-blocks`: only a `done` dependency satisfies a
  task's `depends_on`; a task whose dependency was cancelled is blocked with
  "Dependency cancelled: …" and an `engine.attention_needed` turn
  (`dependency_cancelled`) so a person re-plans it, instead of being started
  as if the prerequisite had shipped; `foreman task cancel` and the dashboard
  cancel refuse a task with a running run while an engine is resident.
- `fix/task-branch-refresh`: every develop visit first merges the default
  branch into the task branch when it is behind and the merge is clean
  (`engine.branch_sync`, mode `refresh`, with `commits_behind`); a refresh
  that conflicts is handed to the developer as guidance (mode
  `refresh_conflict`); an unconcluded merge left by an interrupted pass is
  never aborted (mode `merge_in_progress`); `foreman approve` and `foreman
  deny` exit 75 with an honest message when the resumed workflow pauses on a
  backend quota. New `commits_behind` and `merge_in_progress` git helpers.
- `fix/runner-quota-exhaustion`: a backend usage quota running out mid-step
  (Claude Code's "session limit" result after a rejected `rate_limit_event`)
  is a `QuotaExhaustedError` carrying the reset time; `run_with_retry`
  surfaces it once without retries; the orchestrator pauses the task at its
  current step (`in_progress`, resume point persisted, lease released, no
  loop budget spent) with `Run.failure_type=quota` and an
  `engine.quota_exhausted` event instead of blocking it; `foreman run` exits
  75 with the reset time; `foreman serve` waits for the reset (bounded to
  one minute to six hours) and resumes. `Run.failure_type` is now set for
  quota, preflight, infrastructure, and agent failures. Idle passes are
  narrated once at INFO and repeated at DEBUG.
- `fix/runner-progress-lines`: the Claude Code runner turns progress-only
  stream lines (`system`/`thinking_tokens`, allowed `rate_limit_event`) into
  non-persisted `agent.tick` heartbeats instead of one `agent.tool_use` plus
  one `agent.raw_output` row each; tool results are persisted as a capped
  `agent.tool_result` preview instead of a full-payload tool use; the session
  init line becomes a small `agent.session`; raw lines are capped at 8,000
  characters; unknown message types are kept as raw output only

### Sprint 53 — Phase 0 unattended safety

- opened sprint 53 from Phase 0 of the production readiness review
  (`docs/reviews/production-readiness-review.md`); Phases 1–2 queued in the
  backlog.
- **slice 1, store safety** (`fix/store-concurrency-safety`): migration 14
  rebuilds the gate tables with `ON DELETE` rules so run pruning and task or
  sprint deletion no longer fail on foreign keys, indexes `events(task_id,
  timestamp)`, and replaces scan-based task keys with a per-project sequence
  under a unique index; migrations apply atomically per version; file-backed
  stores use WAL with a busy timeout and retrying hot writes; deletes are
  dependent-aware; the dashboard initializes the schema once; project settings
  are validated at run start, at the dashboard settings endpoint, and at
  `foreman config --set`, with event, run, and prompt retention now explicit
  opt-in settings.
- **slice 2, runner process lifecycle** (`fix/runner-process-lifecycle`): new
  `foreman/runner/process.py` with `ManagedProcess` (pumped stdout and
  stderr, silent-tick wake-ups, own session, process-group terminate and
  kill) and shutdown handlers that stop every registered child and raise
  `EngineShutdown`; both runners rebuilt on it so time and cost gates fire
  while an agent is silent, the Codex handshake is wall-clock bounded, and
  output decodes as UTF-8 with replacement; the orchestrator heartbeats the
  lease on ticks, raises `LeaseLostError` on a refused renewal, and marks the
  run `killed` on shutdown or lease loss while leaving the task resumable;
  `foreman run` exits 130 on SIGTERM or Ctrl+C; `_builtin:run_tests` honors a
  new `test_timeout_seconds` setting and kills its process group on timeout.
- **slice 3, output contract and signals**
  (`fix/output-contract-and-signals`): the completion marker and reviewer
  verdict are read from the agent's final message only; the decision grammar
  accepts `Decision:`/`Verdict:` prefixes, ignores placeholder option lines,
  and turns multiple distinct verdicts or an undeclared verdict into an error
  that triggers the corrective retry; roles declare `[completion] outcomes`,
  `[completion] review_kind`, and `[signals] allowed`, which replace the
  engine's hardcoded reviewer ids in normalization, workflow validation, and
  completion evidence (tiered-review approvals now satisfy the merge guard);
  signals are parsed once, only outside code fences and quotes, accept
  pretty-printed JSON, are deduplicated per step, and are recorded as
  `signal.rejected` when a role may not emit them.
- **slice 4, workflow order and merge gate**
  (`fix/workflow-test-before-review`): every shipped workflow now tests
  before it reviews and ends in a `merge_approval` human gate; gate steps
  declare a `policy`, resolved from the new `merge_approval` (default
  `auto`) and `plan_approval` (default `human`) settings or a per-task
  `executor_overrides.gates` entry; an `auto` gate is approved by the engine
  with a `workflow.gate_auto_approved` event and a `policy:<name>` decision
  record; the reviewer prompt's developer summary now comes from the latest
  agent run instead of the test built-in.
- **slice 5, dashboard minimum safety** (`fix/dashboard-minimum-safety`):
  wildcard CORS removed (explicit `--allowed-origin` allowlist only); a
  shared access token (`--token` / `FOREMAN_DASHBOARD_TOKEN`) guards every
  `/api` route via bearer header, `X-Foreman-Token`, or `?token=` on the
  event stream; non-loopback binds are refused without a token unless
  `--allow-insecure-network`; the manager chat is loopback-only unless
  `--allow-remote-manager` (disabled routes answer 403); project creation
  requires an existing git repository path, optionally inside
  `FOREMAN_DASHBOARD_REPO_ROOTS`; the events page size is capped at 500;
  the frontend sends the token and prompts for it on 401.
- **slice 6, cleanup** (`chore/remove-bootstrap-supervisors`): removed the
  bootstrap supervisor scripts (`scripts/reviewed_claude.py`,
  `scripts/reviewed_codex.py`), their tests, `foreman/supervisor_state.py`,
  and the legacy `finalize_supervisor_merge` path; dropped the unused
  `anthropic` dependency; the autonomous signal contract appears in
  `.foreman/context.md` only for autonomous projects. **Sprint 53 closed**
  with 605 backend and 18 frontend tests passing; archived under
  `docs/sprints/archive/`.

### Milestone

- **Review roadmap complete (Phases 0–7).** The stacked review branches
  (Sprints 49–52) were fast-forwarded to `main` in order on 2026-06-13
  (`62c2e25` → `2ca7b49` → `b53f930` → `35b667c`) and the sprints archived under
  `docs/sprints/archive/`. Full suite: 571 tests passing.

### Frontend

- tied the React dashboard to the finished backend (see
  `docs/reviews/frontend-gap-analysis.md`): the task drawer now shows completion
  evidence (verdict / proof status / score / judged-by + per-criterion
  checklist) and the per-run model; an `engine.attention_needed` supervision
  banner runs one manager turn via `POST …/meta/supervise`; the settings panel
  binds to the real `ProjectSettings` (models/token-economy, criteria judge,
  cost/time gates, `completion_guard_enabled`) and can select
  `development_tiered`; new-task creation carries description, complexity, and
  dependencies.
- fixed frontend bugs: the new-task "Context" field was silently dropped; the
  Run/Stop toggle inferred agent state from task status instead of the
  authoritative `agent_running` field; the settings panel wrote inert keys and
  offered a Codex meta-backend option that broke the manager; the active-sprint
  header showed a dead "Stop" button when idle — it is now a Run↔Stop toggle so
  an idle sprint exposes a usable "Run".
- backend: `POST /api/sprints/{id}/tasks` (`create_task`) now accepts
  `description`, `complexity`, and `depends_on` (matching the CLI); `get_task`
  serializes `completion_evidence`.

### Task keys + dependency picker

- added Jira-style per-project task keys (`FOR-102`): migration 13
  (`projects.task_key_prefix`, `tasks.task_key`), write-once key assignment in
  `ForemanStore.save_task` with a per-project sequence, a derived prefix
  (`derive_task_key_prefix`), and a one-time backfill for existing tasks. Keys
  are surfaced in the task card, the detail drawer, the active-sprint list, and
  dependency chips, and in the `get_task` / `list_sprint_tasks` / `create_task`
  payloads.
- replaced the dependency checkbox list with a Jira/Linear-style **search-to-add
  picker**: type to filter by key or title, selected dependencies render as
  removable chips (key shown, full title on hover). Scales to large sprints and
  matches the form styling.

### Frontend UX (Tier 3 polish)

- surfaced `zero_cost_token_runs`: token totals in the sprint status bar and the
  topbar now show "cost unknown for N runs" so third-party (zero-cost) endpoints
  read honestly.
- consistency pass: unified the inline-card close control to the standard `×`
  glyph and normalized remaining lowercase copy ("Loading…").
- landing copy: replaced the dev-jargon project-overview subtitle
  ("SQLite-backed project state, active sprint summaries, and aggregate engine
  totals.") with plain language, and reframed the project-card footer's raw
  `task_selection_mode · workflow_id` (`directed · development_tiered`) through
  new `formatSelectionMode` / `formatWorkflowLabel` helpers
  (e.g. "Directed · Tiered workflow").

### Frontend layout polish

- project overview: "+ New project" is now a dashed add-tile at the end of the
  project grid instead of a header button.
- project view: the manager panel opens by default and can be resized with a
  drag handle (360–820 px); project content sits in a centered 1080 px measure;
  queue task-row status hugs the title with a middot separator; the activity
  composer uses the accent send button.

### Frontend UX (Tier 2 cont.)

- unified the three task-creation surfaces (New Task modal, New Sprint modal
  initial tasks, inline queue editor) on a shared `TaskFormFields` component so
  they no longer diverge in capability; `create_sprint` initial tasks persist
  complexity.
- meta-agent panel: paginated history with a "Load older messages" control,
  a `supervision` origin badge on engine-triggered turns, and a model-agnostic
  "Manager — Planning & supervision" header (was hardcoded "Claude Code").
- added a **Roles** topbar surface (`RolesModal`) to inspect and edit role
  model / backend / permission mode via `GET`/`PATCH /api/roles`.
- normalized status casing (sprint badges, queue task rows now Title-Cased) and
  tidied empty-state copy.

### Frontend UX (Tier 2)

- Approve/Deny are now scoped to tasks actually paused at a human gate, via a
  new backend `awaiting_human_gate` flag on the task payloads (computed from the
  task's current workflow step role); tasks blocked for other reasons
  (cost/time/loop/evidence) show an explanatory note instead of approve/deny
  buttons that wouldn't apply.
- the sprint board shows a **Cancelled** lane when the sprint has cancelled
  tasks (previously they vanished from the board).
- sprint title and goal gained visible ✎ edit buttons (previously editable only
  via an undiscoverable double-click); planned sprint cards show an expand
  chevron + "Click to expand" affordance so they're distinguishable from
  navigate-on-click active/archived cards.

### Frontend correctness & polish

- fixed the New Task form offering an invalid `bug` task type (which the backend
  rejected with a 400) and omitting `fix`/`docs`/`spike`; the chip list and the
  `getTaskTypeClass` colour map now match the backend `TASK_TYPES`.
- removed the two dead activity filters (`File changes`, `Review` matched event
  types the engine never emits); the feed now filters into Agent / Workflow /
  Decisions / Human, every bucket populated, and the new roadmap events
  (`engine.attention_needed`, `engine.completion_evidence`,
  `workflow.model_selected`, guard/gate events) get readable summaries.
- "Running" now consistently means a live agent (`agent_running`) across the
  landing cards, the topbar engine status, and the breadcrumb — resolving the
  contradiction with the Run/Stop control; the breadcrumb sprint dropdown no
  longer miscolours `cancelled`.
- relabelled the misleading "{n} awaiting approval" project badge to "{n}
  blocked"; aligned the sprint modal's task "Context" field to "Description";
  moved the evidence/supervision colours onto the theme tokens.

### Fixed

- supervision now emits the full attention-trigger taxonomy: a completion/merge
  guard block whose proof gate failed raises `engine.attention_needed` with
  trigger `evidence_failed` (vs. the generic `task_blocked`), and a sprint that
  resolves while the engine stops (supervised/directed handoff, or no further
  work) raises trigger `sprint_resolved`. Previously only `task_blocked` and
  `loop_limit` were emitted, so two triggers defined in the digest never fired.

### Documentation

- added `docs/MANUAL.md`, a complete operator's guide (install, quickstart, CLI
  reference, roles/workflows, multi-model fleet, completion evidence + proof
  gate, tiered review, meta-agent + supervision, dashboard HTTP API, settings,
  event taxonomy, troubleshooting); README now points to it.
- added `docs/reviews/review-md-backend-audit.md`, the independent backend audit
  of the `review.md` implementation.

### Added

- supervision turns and transport polish (sprint 52, review Phases 6–7):
  `foreman/digest.py` `build_attention_digest`; an `engine.attention_needed`
  event emitted exactly once when a task transitions to blocked (loop-limit and
  signal-blocker paths tagged with their trigger); a
  `POST /api/projects/{id}/meta/supervise` endpoint that runs one
  `origin="supervision"` meta turn from the digest, gating mutation on
  `autonomy_level` and rejecting replayed events with 409;
  `ForemanStore.data_version()` with `data_version`-gated SSE and `foreman
  watch` polling (interval lowered to 0.25s); persisted `Run.retry_count` from
  `agent.infra_error` events; the token-economy project settings registered in
  `ProjectSettings`; and ADR-0010
- token-economy evidence and tiered review (sprint 51, review Phases 4–5):
  `foreman/judge.py` with the keyword heuristic as the single owner plus an
  opt-in cheap-model criteria judge (direct Anthropic-compatible HTTP call,
  head/tail diff truncation, heuristic fallback on any error);
  `CompletionEvidence.judged_by` surfaced in the `engine.completion_evidence`
  event; the new `escalate` reviewer outcome; `triage_reviewer` and
  `frontier_reviewer` roles; a `{completion_diff}` curated-diff prompt payload
  for decision roles (`review_diff_max_chars` setting); and the
  `development_tiered` workflow (develop → triage → escalate-to-frontier review)
- per-task executor overrides and a model-escalation ladder (sprint 50, review
  Phase 3): migration 12 (`executor_overrides_json`, `complexity` on tasks);
  `Task.executor_overrides`/`Task.complexity`; role `[agent] model_ladder`;
  the pure `resolve_step_model` model-resolution function wired into the
  workflow loop and native runner with a `workflow.model_selected` event per
  agent step; architect `complexity` persisted from `signal.task_created`;
  `foreman task add --complexity`; `foreman task override` CLI; and
  `executor_overrides` on the dashboard `PATCH /api/tasks/{id}` plus task
  payloads
- durable, store-backed meta-agent chat (sprint 49, review Phase 2): migration
  11 (`meta_sessions`, `meta_turns`); store methods for session/turn
  persistence and cursor paging; a compact `build_state_header()` snapshot
  rebuilt every turn; a first-turn operating contract; crash-safe assistant-turn
  persistence; a configurable `meta_agent_model` setting; `limit`/`before`/
  `has_more` paging on the meta history endpoint
- `foreman task add --description`, `--sprint SPRINT_ID`, and `--depends-on`
  (validated against tasks in the same project)
- Foreman-specific repo instructions in `AGENTS.md`
- active sprint and backlog docs for the first Foreman implementation slice
- repository templates for PR summaries, checkpoints, and sprint archives
- `pyproject.toml` and the initial `foreman/` package scaffold
- a runnable CLI shell covering the spec-aligned command surface
- typed SQLite models and a spec-shaped `foreman.store` persistence layer for
  projects, sprints, tasks, runs, and events
- shipped declarative `roles/*.toml` and `workflows/*.toml` defaults
- a persisted orchestrator loop plus explicit built-in execution seams
- repo-local `.foreman.db` discovery with explicit `--db` override support
- FastAPI, uvicorn, and HTTP client dependencies for the dashboard backend
- a dedicated React and Vite dashboard frontend workspace in `frontend/`
- `foreman init` defaulting to `<repo>/.foreman.db` for repo scaffold
  generation and persisted project initialization
- runtime context projection in `.foreman/context.md` and `.foreman/status.md`
- persisted human-gate approve and deny commands
- native Claude Code and Codex runners in `foreman/runner/`
- store-backed monitoring commands in `foreman.cli` for `board`, `history`,
  `cost`, and `watch`
- `docs/adr/ADR-0001-runner-session-backend-contract.md`
- `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
- `foreman/dashboard.py` with dashboard HTML shell and direct JSON endpoints
- dashboard task detail, activity feed, human message input, activity filter,
  project switcher, and approve or deny actions
- a dedicated dashboard sprint event stream for incremental live activity
  updates
- native runner task-lease heartbeats during streamed Claude/Codex execution
- `foreman/executor.py` and `tests/test_executor.py`
- end-to-end runtime coverage for the opt-in `development_secure` workflow
  plus secure workflow initialization coverage in the CLI
- explicit native backend preflight validation for Claude Code and Codex
- spec-aligned event-retention pruning for old project events
- live-tail `foreman watch` support across project, sprint, and run scopes
- `docs/adr/ADR-0003-web-ui-api-boundary.md`
- `docs/adr/ADR-0004-dashboard-backend-framework.md`
- `docs/adr/ADR-0009-multi-model-endpoints-via-role-env.md`
- per-role `[agent.env]` resolution for native runner environment injection
- `roles/developer_worker.toml` as the sequential worker-model role example
- production-hardening audit and detour planning docs
- `foreman/dashboard_service.py` as the extracted dashboard service layer
- `foreman/dashboard_backend.py` as the FastAPI dashboard transport
- `scripts/dashboard_dev.py` as the combined local dashboard frontend and
  backend launcher
- `frontend/src/App.test.jsx` and the frontend bundle build validation path
- dashboard transition checkpoint notes while the embedded shell was being
  replaced
- `docs/checkpoints/react-dashboard-foundation.md`

### Removed

- obsolete `foreman/executor.py` and `tests/test_executor.py`; the orchestrator
  native runner path is the maintained execution surface

### Changed

- repurposed the transplanted project-memory docs from Apparatus to Foreman
- aligned the autonomous wrapper scripts and repo validation expectations with
  `docs/specs/engine-design-v3.md` and
  `docs/mockups/foreman-mockup-v6.html`
- completed `sprint-01-foundation`, `sprint-02-orchestrator`,
  `sprint-03-scaffold`, and `sprint-04-context-projection`
- completed `sprint-05-human-gates`, `sprint-06-claude-runner`, and
  `sprint-07-codex-runner`
- completed `sprint-08-monitoring-cli`, archived it, and advanced project
  memory to the runner session and backend ADR sprint
- completed `sprint-09-runner-session-backend-adr`, archived it, and advanced
  project memory to the dashboard implementation sprint
- completed `sprint-10-dashboard-implementation`, archived it, and advanced
  project memory to the multi-project dashboard polish sprint
- completed `sprint-11-multi-project-dashboard-polish`, archived it, and
  advanced project memory to the dashboard approve or deny integration sprint
- completed `sprint-12-dashboard-approve-deny-integration`, archived it, and
  advanced project memory to the persistent-session reload sprint
- completed `sprint-13-persistent-session-reload`, archived it, and advanced
  project memory to the dashboard streaming transport sprint
- completed `sprint-14-dashboard-streaming-transport`, archived it, and
  advanced project memory to the engine DB discovery sprint
- completed `sprint-15-engine-db-discovery`, archived it, and advanced project
  memory to the security review workflow sprint
- completed `sprint-16-security-review-workflow`, archived it, and advanced
  project memory to the native backend preflight sprint
- completed `sprint-17-native-backend-preflight-checks`, archived it, and
  advanced project memory to the event-retention pruning sprint
- completed `sprint-18-event-retention-pruning`, archived it, and advanced
  project memory to the watch live-tail alignment sprint
- completed `sprint-19-watch-live-tail-alignment`, archived it, and advanced
  project memory to the migration framework bootstrap sprint
- tightened repo instructions so bootstrap status no longer permits
  prototype-grade implementation decisions
- replanned the next work as a production-hardening detour covering dashboard
  API extraction, React frontend replacement, stub removal, and delayed
  migration work
- completed `sprint-21-dashboard-api-extraction`, archived it, and advanced
  project memory to the dashboard backend foundation sprint
- extracted dashboard reads, actions, and incremental stream payload assembly
  into `foreman/dashboard_api.py` while keeping the current shell functional
- completed `sprint-22-dashboard-backend-foundation`, archived it, and
  advanced project memory to the React dashboard foundation sprint
- replaced the raw dashboard stdlib server with a uvicorn-backed FastAPI
  backend while preserving the current shell and route surface
- completed `sprint-23-react-dashboard-foundation`, archived it, and advanced
  project memory to the product-surface hardening sprint
- replaced the embedded dashboard shell with a dedicated React frontend,
  built asset delivery, and frontend-aware dashboard validation
- pruned redundant dashboard transition checkpoint and PR-summary files now
  that sprint archives and the dedicated frontend checkpoint are the durable
  history
- renamed the dashboard runtime wrapper to `foreman/dashboard_runtime.py` and
  the extracted dashboard service layer to `foreman/dashboard_service.py`
- added frontend-dev support to `foreman dashboard`, Vite `/api` proxying for
  `npm --prefix frontend run dev`, and a one-command
  `npm --prefix frontend run dev:full` workflow
- removed the remaining `handle_stub` product-surface fallbacks by
  implementing the shipped `project`, `sprint`, `task`, `run`, and `config`
  CLI behaviors with direct store or orchestrator integration
- expanded CLI subprocess coverage around sprint activation and completion,
  task lifecycle operations, project inspection, config updates, and direct
  run invocation
- reconciled the loose feature and recovery branches into an integrated
  mainline candidate and restored missing repo-memory artifacts from the
  runner-session ADR branch
- closed the most visible product-surface gaps: settings panel, sprint
  creation, and task creation now run end-to-end from React components
  through FastAPI endpoints to SQLite persistence
- added 15 integration tests covering settings read/update validation, sprint
  creation, and task creation through both the service layer and FastAPI
  transport
- introduced an explicit schema migration framework in `foreman/migrations.py`
  and `foreman/store.py`: version-tracked migrations replace the old bootstrap
  DDL, `initialize()` now upgrades existing databases to the latest schema
  version automatically
- added `docs/adr/ADR-0005-schema-migration-strategy.md` documenting the
  append-only migration list, `schema_migrations` tracking table, and
  `ForemanStore.migrate()` / `schema_version()` API
- added `tests/test_migrations.py` with 17 tests covering migration list
  integrity, fresh install, idempotency on both in-memory and file databases,
  incremental upgrade from a partially-migrated store, and schema version
  accuracy
- added migration 2 (`idx_runs_project_completed`) enabling efficient run
  retention queries; `test_partial_db_upgraded_to_latest` now passes
- added `ForemanStore.prune_old_runs()` to hard-delete terminal runs and their
  cascaded events older than a cutoff while protecting blocked/in-progress tasks
- added `ForemanStore.strip_old_run_prompts()` to null out `prompt_text` on old
  terminal runs while preserving run records and telemetry
- expanded orchestrator startup pruning via `prune_old_history()` reading
  `run_retention_days` and `prompt_retention_days` project settings; emits
  `engine.run_pruned` and `engine.prompt_stripped` lifecycle events
- added `tests/test_run_retention.py` with 19 tests covering deletion,
  active-work protection, cascade event removal, and prompt stripping
- hardened active-run crash recovery so stale task leases are force-expired
  when a run is recovered and live holders are identified by recent lease
  heartbeats
- added browser-driven E2E dashboard validation via Playwright and Chromium:
  `tests/test_e2e.py` with 20 tests covering dashboard load, project and sprint
  navigation, task detail drawer, settings panel, sprint creation, and task
  creation end to end against a live FastAPI server and seeded SQLite database
- added `playwright` and `pytest-playwright` to `pyproject.toml` as optional
  `e2e` dependencies
- implemented `task_selection_mode="autonomous"` in `ForemanOrchestrator`:
  `select_next_task()` now dispatches to `_select_next_task_autonomous()` for
  autonomous projects; resumes in-progress tasks, then creates placeholder tasks
  up to the per-sprint `max_autonomous_tasks` limit (default 5)
- added 8 tests in `AutonomousTaskSelectionTests` covering placeholder creation,
  in-progress resume, no-sprint, limit enforcement, human-task exclusion,
  directed-mode unchanged, and unknown-mode error
- added `foreman db version` — shows current schema version; handles missing
  `schema_migrations` table on pre-migration-framework databases
- added `foreman db migrate` — applies pending schema migrations via
  `store.initialize()` and reports each applied version with description
- changed `ForemanStore.initialize()` to return `list[int]` (backward-compatible)
- added 7 tests in `DbCommandTests`
- completed `sprint-30-wire-dead-surfaces`: wired Stop agent button to
  `POST /api/projects/{id}/agent/stop`; added `PATCH /api/sprints/{id}` for
  lifecycle transitions (planned→active, active→completed/cancelled) with
  `started_at`/`completed_at` timestamps; added `PATCH /api/tasks/{id}` for
  `description` and `priority` updates; extended `get_task` run serialization;
  added sprint status badge and Start/Complete buttons in sprint view header;
  10 tests in `DashboardSprintLifecycleTests`
- completed `sprint-31-backlog-items`: sprint creation with inline initial tasks
  via `initial_tasks` in API body; task cancellation (`POST /api/tasks/{id}/cancel`,
  Cancel task button in drawer); task dependency display in drawer via
  `depends_on_task_ids`; event log load-more with `before_event_id` cursor and
  `has_more` flag; cancelled sprint filter in list and kanban Done column;
  8 tests in `DashboardSprintTaskBacklogTests`
- completed `sprint-32-tier1-editing`: task field editing in `TaskDetailDrawer`
  (title, type, acceptance criteria) via edit mode with chip selector and
  textarea; sprint goal inline editing in sprint header via `update_sprint_fields`;
  activity panel auto-scroll using `useLayoutEffect` and scroll-position tracking;
  `containerRef`/`onScroll` props on `EventList`; 11 tests in
  `DashboardTaskEditingTests`
- completed `sprint-33-tier2-gaps`: `workflow_current_step` added to
  `list_sprint_tasks` response and shown as badge on in-progress task cards and
  in detail drawer; project creation from dashboard via `POST /api/projects` and
  `NewProjectModal`; `foreman run` from dashboard via
  `POST /api/projects/{id}/agent/start` spawning a `foreman run` subprocess with
  double-start prevention; Run ▶ / Stop ■ toggle in sprint header; 9 tests in
  `DashboardTier2Tests`
- completed `sprint-34-task-edit-enforcement`: `update_task_fields` now tracks
  which fields actually changed; emits `human.task_edited` event with
  `changed_fields` payload for `in_progress` and `blocked` tasks; creates a
  synthetic dashboard/edit run if no run history exists (FK safety);
  `getEventCategory` broadened from exact `human.message` match to `human.*`
  prefix; `formatEventSummary` handles `human.task_edited`; 6 tests in
  `DashboardTaskEditEventTests`
- completed `sprint-35-dashboard-crud-polish`: fixed board-view filter leak
  (status filter buttons and sort conditioned on list view mode); added
  `ForemanStore.delete_task()` and `delete_sprint()` with FK-safe cascade
  (events → runs → tasks → sprint); `DELETE /api/tasks/{id}` and
  `DELETE /api/sprints/{id}` routes; delete buttons in `TaskDetailDrawer` and
  on sprint cards with confirm guard; sprint title inline editing in sprint
  header; `order_index`, `started_at`, `completed_at` added to all sprint API
  responses; `order_index` editable via `PATCH /api/sprints/{id}`; ↑/↓ reorder
  buttons on sprint cards swap adjacent `order_index` values; sprint list sort
  fixed to use `order_index` (was using undefined `order` field); `formatDate`
  added; dates shown on sprint cards and in sprint header stats; 18 new tests
  across `DashboardDeleteTests` and `DashboardSprintOrderTests`; 95 dashboard
  tests and 20 E2E tests all passing
- completed `sprint-36-intervention-and-ordering`: sprint list ordering fixed
  (active/completed above planned); `POST /api/tasks/{id}/stop` route for
  stopping individual in-progress tasks; Stop button on task cards and in
  task detail drawer; Cancel sprint button in sprint view header for active
  and planned sprints; board column equal-width fix (`minmax(0, 1fr)`);
  custom scrollbar styling; duplicate branch name generation fixed in
  orchestrator; 6 new tests in `DashboardInterventionTests`; 95 dashboard
  tests passing
