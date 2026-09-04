# STATUS

## Current sprint

- Active implementation sprint: **sprint 54 — Phase 1: resident engine and
  intake** (`docs/sprints/current.md`), opened 2026-09-04 from Phase 1 of
  `docs/reviews/production-readiness-review.md`.
- Method: slices are planned by hand and executed through Foreman itself
  (`foreman run foreman`) wherever the engine can carry them; findings are
  recorded in `docs/reviews/sprint-54-live-run-notes.md`.
- Latest completed sprint: `sprint-53-phase0-unattended-safety`.
- Last merged branch:
  `feat/task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock`
  (sprint 54 slice 1, merged to `main` at `a462659` by the engine's own
  merge step), then `docs/sprint-54-live-run-1`.
- Current implementation branch: none by hand. Next: sprint 54 slice 2a
  (engine command table) as a dogfood task picked up by `foreman serve
  foreman`.

## Active branches

- `docs/sprint-54-live-run-1` — live-run notes for run 1, sprint doc and
  status updates, `.gitignore` covers a `venv` symlink; merged to `main`
- `feat/task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock`
  — sprint 54 slice 1: `foreman serve`, `foreman/engine_lock.py`,
  `foreman/logs.py`, ADR-0011; merged to `main` at `a462659` by the engine
- `fix/runner-progress-lines` — sprint 54 live-run fix: progress-only
  stream lines are heartbeats, tool results are capped previews; merged to
  `main`
- `docs/sprint-54-open` — opens sprint 54 (Phase 1) and the live-run
  protocol; merged to `main`
- `chore/remove-bootstrap-supervisors` — sprint 53 slice 6, merged to
  `main` at sprint close: bootstrap supervisor scripts and the legacy
  supervisor-merge path removed, unused dependency dropped, sprint archived
- `fix/dashboard-minimum-safety` — merged to `main` at `8074eda`; sprint 53
  slice 5
- `fix/workflow-test-before-review` — merged to `main` at `10333ef`; sprint
  53 slice 4
- `fix/output-contract-and-signals` — merged to `main` at `2d9829a`; sprint
  53 slice 3
- `fix/runner-process-lifecycle` — merged to `main` at `79d499a`; sprint 53
  slice 2
- `fix/store-concurrency-safety` — merged to `main` at `9d23fe0`; sprint 53
  slice 1
- `docs/minimax-smoke-closeout` — updates repo memory after merging the
  MiniMax role-env smoke to `main`
- `feat/worker-fleet-minimax-smoke` — merged to `main` at `07649e6`; retained
  on origin as the completed MiniMax role-env implementation branch
- `docs/phase0-closeout-status` — merged to `main` at `6f149f5`; retained on
  origin as the Phase 0 closeout docs branch
- `fix/review-phase0-correctness` — merged to `main` at `5883075`; retained on
  origin as the completed Phase 0 implementation branch
- `fix/backend-correctness-hardening` — closes residual backend correctness
  gaps found after transcript logging by tightening persisted builtin event
  schema versioning and adding regression coverage for strict outcome
  normalization, lease fencing, lease uniqueness, and crash-recovery token
  redaction

## Current focus

- Sprint 54 (Phase 1): `foreman serve` resident worker, engine command
  table, intake endpoint, policy matrix v1, planner step, worktree per task.
  Pull-request integration (GitHub, via `gh`) is queued for sprint 55;
  login and notifications wait on the identity-provider and channel
  decisions.
- Phase 0 of the production readiness review is complete: an unattended run
  is safe on one machine.

## Latest update — sprint 54 live run 1 closed

- Slice 1 was carried end to end by the engine on the dogfood project:
  develop (Opus 5, 24.5 min), built-in tests, code review (Sonnet 4.6),
  a human `deny` with two corrections, a corrective pass on the resumed
  session, a merge conflict against a moved `main` resolved by a third pass,
  and the engine's own `--no-ff` merge at `a462659`. 49 minutes, $21.96.
- Twenty-four observations are recorded in
  `docs/reviews/sprint-54-live-run-notes.md`. The structural ones: the
  heuristic evidence rates correct work "weak" and reviewers are told to
  weigh it; shared markdown memory files conflict by construction between
  overlapping branches; the engine merges straight into the operator's
  checkout (an ignored `venv` was destroyed by a symlink commit during the
  run and rebuilt); `tests/test_cli.py` reinstalls the package into the
  shared venv from whatever checkout runs it.
- `.gitignore` now ignores a bare `venv` entry as well as the directory.

## Previous update — sprint 54 slice 1: resident engine and project lock

- Branch
  `feat/task-add-foreman-serve-resident-engine-worker-with-a-project-engine-lock`.
  `foreman serve <project-id> [--poll-seconds N] [--once]` keeps the engine
  resident: one `run_project` pass per iteration, and an idle pass waits on
  `PRAGMA data_version` or the poll interval instead of exiting.
- New `foreman/engine_lock.py` enforces one engine per project through a lease
  with `resource_type="engine"` — no migration needed, the `leases` table
  already supports arbitrary resource types. Renewal runs on a daemon timer
  thread with its own store connection, deliberately independent of agent
  output. `foreman run` takes the same lock.
- New `foreman/logs.py` emits JSON lines on stderr; `serve` never prints, and
  the orchestrator mirrors every persisted event to the same logger at the
  level `event_log_level()` assigns its family — the narrative at INFO, the
  agent output firehose at DEBUG, so a resident engine's log stays readable.
  The families `fix/runner-progress-lines` introduced land correctly without a
  change: `agent.tick` and `agent.tool_result` at DEBUG, `agent.session` at
  INFO.
- A failing task is blocked with an `engine.attention_needed` turn and the
  service continues after a doubling backoff; SIGTERM settles the run as
  `killed`, releases the lock, and exits 0 (`foreman run` keeps 130).
- Recorded as ADR-0011. Suite after merging `main`: 656 tests, OK
  (1 skipped: `tests/test_e2e.py` needs playwright).
- **Known gap, closed by the next slice:** the dashboard's Run button still
  spawns a `foreman run` subprocess, which now competes for the engine lock
  rather than cooperating with a resident worker. Slice 2 replaces it with the
  engine command table.

## Previous update — sprint 54 live run 1: runner progress lines

- Found while the engine ran sprint 54 slice 1 on itself: the current Claude
  Code CLI streams `system`/`thinking_tokens` counters about twice a second
  while the model reasons, and the runner persisted each as an
  `agent.tool_use` (tool `claude.stream_event`) plus an `agent.raw_output`
  row; tool results (`user` lines) were persisted twice with their full
  text (up to 26 KB each). Four minutes of one developer step wrote about
  400 rows and 550 KB.
- Branch `fix/runner-progress-lines`: progress lines become non-persisted
  `agent.tick` heartbeats, tool results become a capped `agent.tool_result`
  preview, the init line becomes `agent.session`, raw lines are capped at
  8,000 characters, and unknown message types are no longer reported as
  tool uses. See `docs/reviews/sprint-54-live-run-notes.md`.

## Previous update — sprint 53 slice 6: cleanup and sprint close

- Branch `chore/remove-bootstrap-supervisors`. Removed
  `scripts/reviewed_claude.py`, `scripts/reviewed_codex.py`, their tests,
  `foreman/supervisor_state.py`, and the orchestrator's legacy
  `finalize_supervisor_merge` path; `_builtin:mark_done` plus
  `_builtin:merge` is the only completion path. Dropped the unused
  `anthropic` dependency. The autonomous signal contract is rendered into
  `.foreman/context.md` only for autonomous projects. `AGENTS.md` now names
  `foreman run` as the only autonomous entry point and adds the unit suite
  to the baseline validation.
- Sprint 53 closed and archived; checkpoint at
  `docs/checkpoints/2026-09-04-sprint-53-phase0-unattended-safety.md`.
- Validation: 605 backend tests passing (56 removed with the bootstrap
  code), 18 frontend tests.

## Previous update — sprint 53 slice 5: dashboard minimum safety

- Branch `fix/dashboard-minimum-safety`. The dashboard no longer sends
  wildcard CORS headers; an explicit `--allowed-origin` list enables CORS.
  A shared token (`--token` / `FOREMAN_DASHBOARD_TOKEN`) is required on
  every `/api` route once configured (bearer header, `X-Foreman-Token`, or
  `?token=` for the event stream), compared in constant time.
- `dashboard_security_policy` refuses a non-loopback bind without a token
  unless `--allow-insecure-network`, and keeps the manager chat (a
  full-access agent session on the host) loopback-only unless
  `--allow-remote-manager`; disabled manager routes answer 403.
- `create_project` rejects paths that are not existing git repositories and,
  with `FOREMAN_DASHBOARD_REPO_ROOTS`, paths outside the allowed roots;
  the events endpoint caps `limit` at 500.
- The frontend sends the stored token, puts it on the stream URL, and shows
  a token prompt on 401. Bundle rebuilt.
- Validation: 661 backend tests (+12 in `tests/test_dashboard_safety.py`),
  18 frontend tests (+5 in `api.test.js`).

## Previous update — sprint 53 slice 4: workflow order and merge gate

- Branch `fix/workflow-test-before-review`. All four shipped workflows now
  run `develop → test → reviews → merge_approval → merge → done`, so
  reviewers see real test results in the evidence and a red suite never
  reaches a reviewer.
- Human-gate steps can carry a `policy` (`merge_approval` or
  `plan_approval`). The matching project setting, or a per-task
  `executor_overrides.gates` entry, resolves to `auto` (the engine approves
  with a `workflow.gate_auto_approved` event and a `policy:<name>` decision
  record) or `human` (the task pauses for `foreman approve`). Defaults:
  `merge_approval=auto`, `plan_approval=human`.
- The reviewer's `{previous_output}` now comes from the latest agent run
  rather than the latest run, which would have been the test built-in.
- Validation: 648 backend tests passing (+10 in
  `tests/test_workflow_gates.py`; sequence expectations across the suite
  updated to the new order).

## Previous update — sprint 53 slice 3: output contract and signals

- Branch `fix/output-contract-and-signals`. The role contract is applied to
  the agent's final message only: a marker echoed in an early plan no longer
  completes a task, and a reviewer's restated options no longer flip the
  verdict. The decision grammar accepts `Decision:` / `Verdict:` prefixes,
  ignores placeholder option lines, and treats multiple distinct verdicts or
  an undeclared verdict as an error that triggers the corrective retry.
- Roles declare `[completion] outcomes`, `[completion] review_kind`, and
  `[signals] allowed`; the orchestrator, the workflow validator, and the
  evidence builder read those instead of hardcoded reviewer ids. This also
  fixes tiered review: a frontier approval now satisfies the merge guard,
  which previously only passed with the guard disabled.
- Signals are parsed once (not again from the Claude `result` text), only
  outside code fences and quotes, accept pretty-printed JSON, are
  deduplicated per step, and are rejected with a `signal.rejected` event when
  a role is not allowed to emit them.
- Validation: 638 backend tests passing (+18 in
  `tests/test_output_contract.py`).

## Previous update — sprint 53 slice 2: runner process lifecycle

- Branch `fix/runner-process-lifecycle`. New `foreman/runner/process.py`:
  `ManagedProcess` pumps stdout and stderr on threads, yields ticks while
  the child is silent, runs children in their own session, and terminates or
  kills the whole process group; a registry plus `install_shutdown_handlers`
  drain every child on SIGTERM, SIGINT, and exit and raise `EngineShutdown`.
- Both runners are rebuilt on it: time and cost gates fire on silent ticks,
  the Codex handshake is wall-clock bounded, output decodes as UTF-8 with
  replacement, and an abandoned run generator kills the agent's group.
- The orchestrator heartbeats the lease on `agent.tick` without persisting
  it, raises `LeaseLostError` when a renewal is refused, and settles the run
  row as `killed` on shutdown or lease loss while leaving the task
  resumable. `foreman run` installs the handlers and exits 130 when stopped.
- `_builtin:run_tests` honors `test_timeout_seconds` (default 1800) and kills
  its process group on timeout.
- Validation: 620 backend tests passing (+15 in
  `tests/test_runner_lifecycle.py`, using real subprocesses).

## Previous update — sprint 53 slice 1: store safety

- Branch `fix/store-concurrency-safety`. Migration 14 rebuilds
  `human_gate_decisions` and `decision_gates` with `ON DELETE` rules, adds
  `idx_events_task`, and introduces `projects.task_key_seq` plus a unique
  partial index on task keys after blanking duplicates from the old scan
  allocator.
- `ForemanStore.migrate` now applies each migration's statements and ledger
  row inside one `BEGIN IMMEDIATE` transaction and raises `MigrationError` on
  failure; file-backed stores use WAL, `synchronous=NORMAL`, a 30 s busy
  timeout, and retrying hot writes.
- `delete_task`, `delete_sprint`, and `prune_old_runs` are dependent-aware;
  gate decisions survive run pruning with their run link nulled.
- `ProjectSettings` gained optional run and prompt retention plus
  `max_infra_retries` and `active_run_recovery_timeout_minutes`; event
  retention is opt-in. The orchestrator validates settings at run start and
  refuses a misconfigured project; the dashboard endpoint and
  `foreman config --set` reject invalid values.
- Validation: 605 backend tests passing (+20 in `tests/test_store_safety.py`);
  migration 14 dry-run against a copy of the dogfood database is clean.

## Previous update — frontend↔backend binding

- Branch `feat/frontend-backend-binding`. Closes Tiers 1–2 of the frontend gap
  analysis (`docs/reviews/frontend-gap-analysis.md`): completion-evidence and
  per-run model in the task drawer, an `engine.attention_needed` supervision
  banner wired to `POST …/meta/supervise`, a settings panel rebuilt against the
  real `ProjectSettings` (token economy, judge, gates) with `development_tiered`
  selectable, and richer task creation (description/complexity/dependencies).
- Fixed dropped-context, `agent_running`, and dead/dangerous settings bugs.
  Backend: `create_task` gained description/complexity/depends_on; `get_task`
  serializes completion evidence.
- Validation: backend suite 582 passing (+5); frontend 4 passing (added a
  supervision-banner test, fixed two pre-existing failures); dist rebuilt.

## Latest update — supervision-trigger completion + operator manual

- Branch `feat/supervision-triggers-and-docs`. Closes the one gap found by the
  independent backend audit (`docs/reviews/review-md-backend-audit.md`): the
  orchestrator now emits `engine.attention_needed` with trigger
  `evidence_failed` on a proof-gate-failed guard block and `sprint_resolved`
  when the engine stops at a sprint boundary — previously only `task_blocked`
  and `loop_limit` were raised.
- Added `docs/MANUAL.md`, the complete operator's usage manual, linked from the
  README.
- Validation: full suite 577 passing (was 571; +6 regression tests);
  `scripts/validate_repo_memory.py` clean.

## Latest update — review Phases 6 & 7 supervision and transport

- `feat/supervision-and-transport` (top of the stack) implements review Phases
  6 and 7, completing the review roadmap.
- Engine→manager supervision: `foreman/digest.py`, an
  `engine.attention_needed` event emitted exactly once per block, and a
  `POST /api/projects/{id}/meta/supervise` endpoint that runs one
  `origin="supervision"` meta turn (409 on replay; directed mode is
  recommend-only).
- Transport polish: `ForemanStore.data_version()` gates the SSE and
  `foreman watch` loops (poll interval 0.25s); `Run.retry_count` is now
  persisted from `agent.infra_error` events.
- Token-economy settings registered in `ProjectSettings`; README and ADR-0010
  added.

## Latest update — review Phases 4 & 5 token economy

- `feat/judge-and-tiered-review` (stacked on `feat/executor-overrides-ladder`)
  implements review Phases 4 and 5.
- `foreman/judge.py` owns the keyword heuristic and adds an opt-in cheap-model
  criteria judge (direct Anthropic-compatible HTTP call, head/tail diff
  truncation, heuristic fallback on any error). `CompletionEvidence.judged_by`
  is now recorded and emitted in `engine.completion_evidence`; the heuristic
  path is byte-identical to before when the judge is unset.
- Added the `escalate` outcome, the `triage_reviewer` (cheap) and
  `frontier_reviewer` (frontier, payload-only) roles, a `{completion_diff}`
  curated-diff prompt payload for decision roles, and the `development_tiered`
  workflow (develop → triage → escalate-to-frontier review).

## Latest update — review Phase 3 executor overrides + escalation ladder

- `feat/executor-overrides-ladder` (stacked on `feat/meta-agent-persistence`)
  implements review Phase 3.
- Migration 12 adds `tasks.executor_overrides_json` and `tasks.complexity`;
  `Task` carries `executor_overrides` and `complexity`.
- Roles gained an optional `[agent] model_ladder`; the new pure
  `resolve_step_model` resolves a per-step model by precedence (override →
  ladder → role model → project default → none) and the workflow loop and
  native runner now emit a `workflow.model_selected` event per agent step.
- The architect `complexity` from `signal.task_created` is now persisted and
  feeds the ladder start index.
- New CLI: `foreman task add --complexity` and `foreman task override`; the
  dashboard `PATCH /api/tasks/{id}` accepts a validated `executor_overrides`
  object and task payloads expose `executor_overrides`/`complexity`.

## Latest update — review Phase 2 manager hardening

- `feat/meta-agent-persistence` implements review Phase 2: the meta-agent chat
  panel is now durable and store-backed.
- Migration 11 adds `meta_sessions` and `meta_turns`; the in-memory
  `_sessions` registry is removed and chat history plus Claude Code session
  resumption now survive dashboard restarts.
- Every turn rebuilds a compact `build_state_header()` world snapshot from
  SQLite, and the first turn of a session injects `build_operating_contract()`
  enumerating the manager's exact `foreman` CLI surface and hard rules.
- The assistant turn is persisted in a `finally` path flagged `interrupted` on
  error/cancel, so a crash never silently drops a turn; `meta_agent_model`
  selects the manager model.
- `foreman task add` gained `--description`, `--sprint`, and `--depends-on` so
  the contract's promotion surface is honest.
- Full local validation passed:
  `./venv/bin/python -m unittest discover -s tests` ran 528 tests.

## Latest update - active-run lease heartbeat recovery merged

- MiniMax M3 through Claude Code drafted the core implementation and tests on
  `feat/active-run-lease-heartbeat-recovery`; Codex is supervising review,
  cleanup, docs, validation, and merge.
- `feat/active-run-lease-heartbeat-recovery` was fast-forward merged to
  `main` and pushed to `origin/main` at `5fbfc26`.
- Native runner event streams now periodically renew the task lease while a
  step is still running, instead of waiting until the workflow step returns.
- Stale run recovery now treats old task-lease heartbeats as non-live holder
  evidence and force-expires the recovered task lease before resetting the task
  to `todo`.
- New regression tests cover forced lease expiry, crash-recovery payload
  redaction, live-holder protection, and native stream heartbeat behavior.
- Full local validation passed:
  `./venv/bin/python -m unittest discover -s tests -v` ran 518 tests.

## Latest update — MiniMax worker-model smoke merged

- `feat/worker-fleet-minimax-smoke` was fast-forward merged to `main` and
  pushed to `origin/main` at `07649e6`.
- The branch passed full local validation:
  `./venv/bin/python -m unittest discover -s tests -v` passed with 513 tests.
- MiniMax M3 is now verified through Claude Code for a sequential
  edit-capable run on the host-side configuration.

## Previous update — MiniMax worker-model smoke

- Created `feat/worker-fleet-minimax-smoke` from `main`.
- Implemented per-role `[agent.env]` loading and `AgentRunConfig.env`.
- Added `foreman.runner.env.resolve_env()` for literal values, required
  `env:NAME`, optional `env:NAME?fallback`, and `_DIR` or `_PATH` expansion.
- Claude Code and Codex runners now pass merged process env only when a role
  env is configured, preserving previous fake-runner behavior otherwise.
- The orchestrator resolves role env before native execution; missing required
  env vars produce one preflight-style `agent.error` with
  `preflight_failed=true` and do not enter runner retry loops.
- Added `roles/developer_worker.toml` with commented MiniMax settings and a
  distinct `CLAUDE_CONFIG_DIR` example.
- Manual MiniMax findings:
  - sandboxed Claude CLI smoke timed out in API retries with `apiKeySource:
    none`, so it was not seeing normal host auth/config.
  - escalated host-side `claude --print --model minimax-m3` returned
    `minimax-ok`.
  - escalated host-side edit smoke with `--permission-mode bypassPermissions`
    used Claude Code `Write`, created `/tmp/foreman-minimax-smoke/minimax_smoke.txt`,
    and returned `TASK_COMPLETE`.

## Previous update — review Phase 0 merged

- `fix/review-phase0-correctness` was fast-forward merged to `main` and pushed
  to `origin/main` at `5883075`.
- The Phase 0 branch now has full local validation:
  `./venv/bin/python -m unittest discover -s tests -v` passes with 500 tests.
- Simple Minimax M3 Claude Code calls and a direct `ClaudeCodeRunner` smoke
  work, but a delegated edit attempt hung without output. The next slice should
  turn that into a repeatable smoke and fix the runner/config gaps before
  relying on unattended cheap-model edits.

## Previous update — review Phase 0 implementation

- Bootstrapped the missing local `./venv` with Python 3.12, installed Foreman
  editable, initialized a local `.foreman.db`, created and activated the
  `Review Phase 0 correctness` sprint, and added the Phase 0 task through
  Foreman's own CLI.
- Implemented the open Phase 0 fixes:
  - `signal.task_created` now receives the active `Run` and persists
    `engine.task_created` against that run.
  - `foreman waive-merge` imports `uuid4`; a CLI regression creates an active
    merge waiver against a temp git repo.
  - dashboard human/edit/stop events share a FK-safe synthetic-run helper and
    use the latest run when one exists.
  - dashboard Run/Stop process tracking moved to a module-level locked
    registry; Stop terminates registered subprocesses and project payloads
    expose `agent_running`.
  - completion evidence is built only for decision-extracting roles and is
    rebuilt when the task branch head changes.
  - dashboard task cancellation now clears stale resume fields and sets
    `completed_at`.
  - removed obsolete `foreman/executor.py` and `tests/test_executor.py`.
- Added a defensive completion-evidence guard for missing repo paths so
  supervisor finalization records weak evidence instead of crashing when a
  stored repository path cannot be inspected.
- Cleared the remaining full-suite validation blockers:
  - signal-parser tests now match the current diagnostic-event behavior.
  - CLI tests now tolerate the repo-local discovery path and current secure
    workflow transition count.
  - `scripts/reviewed_codex.py` falls back to a temp run directory when
    `.codex/run` is read-only during import.
  - optional e2e tests skip cleanly when `pytest` is absent from a minimal venv.
- `./venv/bin/python -m unittest discover -s tests -v` now passes locally with
  500 tests.
- Verified Minimax M3 works through Claude Code for simple `--print` calls and
  through `ClaudeCodeRunner`; a delegated edit attempt through Claude Code hung
  without output, so unattended Minimax editing still needs a focused Phase 1
  worker-fleet smoke.

## Previous update — review integration

- `fix/backend-correctness-hardening` was fast-forward merged to `main` at
  `b396fda` and pushed to `origin/main`.
- `docs/specs/review.md` is now treated as the implementation review roadmap.
  It is not a replacement for `docs/specs/engine-design-v3.md`, which remains
  the product behavior source of truth.
- The review's Phase 0 list was compared against current code:
  - already fixed on `main`: `engine.role_policy` is emitted after run
    creation; merge conflicts now use the explicit `conflict` outcome and
    `completion:conflict` routing.
  - still open and next up: `signal.task_created` references an unbound `run`;
    `foreman waive-merge` uses `uuid4()` without importing it; dashboard human
    messages can persist invalid `run_id="none"` events; dashboard run process
    tracking is per-request and cannot reliably stop spawned runs; completion
    evidence is built too broadly and can go stale; dashboard task cancellation
    leaves workflow resume fields intact; the dead `foreman/executor.py` path
    remains.
- Phase 1+ from the review becomes the forward path after Phase 0: per-role
  environment injection for model fleet support, store-backed manager chat,
  per-task executor overrides and escalation ladders, judged completion
  evidence, tiered review, supervision turns, and SSE cleanup.

## Previous update — backend correctness hardening

- Moved the untracked backend bug note out of `docs/specs/` and preserved it as
  `docs/checkpoints/2026-04-29-backend-correctness-bug-triage.md`, because
  `docs/specs/` is reserved for authoritative product direction.
- Confirmed several alleged bugs were already fixed on `main`: secure merge
  conflict routing, proof-status merge gating, review/security merge gating,
  branch-violation event persistence, crash-recovery token redaction, lease
  fencing, and autonomous `task_started` post-developer-step enforcement.
- Fixed the remaining confirmed persistence gap: streamed builtin events now
  get `schema_version` before they are written to SQLite.
- Fixed conflict recovery so `_builtin:merge` returns the explicit `conflict`
  outcome and directed recovery can resume from a clean checkout left on
  `main` after an aborted merge.
- Fixed reviewer routing after strict outcome normalization: reviewer and
  security-reviewer runs now use reviewer-decision normalization, while
  unknown generic agent outcomes still normalize to `error`.
- Tuned completion proof status so explicit code-review approval plus passing
  tests can satisfy semantic criteria coverage for small real diffs, avoiding
  deadlocks from heuristic criteria matching misses.
- Updated regression tests so they assert the intended safety behavior:
  unknown agent outcomes normalize to `error`; informal reviewer approvals do
  not approve; crash-recovery events do not persist lease tokens; lease fencing
  increments on reacquisition; the active-resource lease index is unique.

## New findings this session

- the “phantom file” behavior was caused by a real hidden host-side process,
  not synthetic heartbeat spam
- host-level inspection revealed the still-running chain:
  - `/home/datision/projects/foreman/venv/bin/python ./venv/bin/foreman run foreman`
  - child `claude --print --verbose --output-format stream-json ...`
- that hidden run continued writing real `agent.file_change` and
  `agent.tool_use` events into SQLite even when the sandboxed shell could not
  see the process via narrow `ps` filters
- the run was stopped explicitly before sprint closeout so we could take over
  the remaining work manually and start the logging slice from a quiet baseline

## Completed this session (sprints 36–46)

- completed `sprint-45-supervised-convergence-validation`
- ran a supervised Foreman session end to end against the live repository
- verified queue activation, task execution, review, merge, and SQLite
  completion state through a real session rather than a simulated path
- merged regression-test and repo-memory updates; no new `foreman/*.py`
  implementation changes landed from the autonomous run itself
- started `sprint-46-completion-truth-hardening`
- confirmed the real backend gap after sprint 45 is completion-truth
  evaluation, not directed task selection: in directed mode Foreman executes
  the next runnable queued task and currently lacks a first-class structured
  completion-evidence model
- completed `task-completion-evidence-model-in-orchestrator`
- added a `CompletionEvidence` dataclass and evidence builder in
  `foreman/orchestrator.py`; `finalize_supervisor_merge()` now persists
  structured completion evidence and emits an `engine.completion_evidence`
  event
- added `Task.completion_evidence` plus `completion_evidence_json` persistence
  in the SQLite store and migration framework
- hardened `ForemanStore.initialize()` with a narrow additive schema-repair
  step so long-lived local databases recover when a migration ledger entry
  exists without the matching `tasks.completion_evidence_json` column
- raised shipped role and executor cost caps to `$1000.00` so native runs do
  not stop early on environments that do not need per-run USD gating
- queued `sprint-47-active-run-lease-and-heartbeat-recovery` as the next
  planned backend sprint ahead of the older deferred planned sprint 8
- fixed native-step ownership and stale-run recovery in sprint 46
  by persisting active workflow steps before native execution, streaming
  native runner events into SQLite as they occur, and using the latest
  persisted event timestamp for timeout-based recovery
- fixed dirty task finalization in sprint 46 so `_builtin:merge` and
  `_builtin:mark_done` refuse success from dirty worktrees or branch states
  with no committed mergeable delta
- fixed malformed output-contract handling in sprint 46 by adding one
  corrective retry for developer outputs missing `TASK_COMPLETE` and reviewer
  outputs that do not parse to `APPROVE`, `DENY`, or `STEER`
- fixed sprint-46 merge-conflict recovery loops so merge conflicts are
  distinct workflow outcomes, stale existing task branches can be refreshed
  against latest `main`, and conflict-resolution passes go back through code
  review before merge
- finished `task-completion-truth-contract-docs` manually after repeated
  looped reruns by merging the docs branch into local `main`, reconciling the
  task state in SQLite to `done`, and correcting the stale workflow smoke-test
  expectation that had kept sending the task back from `test` to `develop`
- finished `task-reviewer-prompt-hardening-with-engine-produced-evidence`
  manually after confirming the feature had already landed in local `main`,
  stopping a hidden host-side rerun, and reconciling the final task row to
  `done`
- completed `sprint-46-completion-truth-hardening`
- completed `sprint-44-supervisor-state-reconciliation`
- introduced shared supervisor finalization seam in `foreman/supervisor_state.py`
  that maps a merged branch back to a tracked task, marks it done, and propagates
  sprint lifecycle; wired `finalize_supervisor_merge` into both reviewed
  supervisors; added post-merge branch safety to reviewed Codex (remembers the
  supervisor merge HEAD and rejects dirty or drifted `main`); added regression
  tests in `test_supervisor_state.py` and `test_reviewed_codex.py`
- completed `sprint-43-backend-run-queue-activation`
- move first-planned-sprint activation into the backend run path so
  `foreman run <project>` can consume queued work without a dashboard-only
  pre-activation shim; add sprint-level cost gating in the orchestrator so
  unattended runs stop when a sprint budget is exhausted; preserve actionable
  runner failure details on blocked tasks and honor the project-level per-run
  time limit setting in native executor config; restore the caller's original
  git branch after clean task runs and blocked failures; treat a live
  `in_progress` task as owning the sprint so Foreman waits instead of starting
  parallel work into the same checkout, and recover only stale `running` runs
  during crash recovery
- completed `sprint-42-dashboard-run-invocation`
- confirmed the dashboard Run subprocess mismatch from the shipped surfaces:
  `DashboardService.start_agent()` spawned `foreman run --project ...` while
  the CLI parser only accepts positional `project_id`
- fixed `DashboardService.start_agent()` to invoke `foreman run <project_id>
  --db ...` and added regression coverage for both project-scope and task-scope
  argv assembly
- completed `sprint-41-sprint-queue-and-advancement`
- wired orchestrator sprint advancement to project `autonomy_level`;
  autonomous mode now auto-activates the next planned sprint and continues,
  while supervised mode emits `engine.sprint_ready` and directed mode stops
  after the sprint completes
- added queue-order lookup via `ForemanStore.get_next_planned_sprint()` and
  made dashboard Run auto-activate the first planned sprint when nothing is
  active
- replaced the old kanban or filter project view with a queue-focused project
  surface around Active, Queue, and Archive; the first queued sprint is styled
  as next up instead of using activation as the ordering signal
- removed the old Start/Promote-to-active behavior; queue order is now the
  intent signal for what runs next
- completed `sprint-40-meta-agent-panel`
- replaced the sprint-39 planner stub with a correct meta agent: persistent
  Claude Code subprocess per project, right-side collapsible sidebar panel on
  the project sprint list view matching the Activity panel pattern
- panel spans full height, session history preserved across open/close, streams
  text and tool-use chips, Clear button wipes in-memory session
- fixed silent subprocess failure (`--output-format stream-json` requires
  `--verbose`; Claude Code exits silently without it)
- sprint list filters now scope to executed sprints only; planned sprints always
  visible; removed nonsensical "Planned" filter button
- cleaned up dead `"done"` sprint status in card classes, board column filter,
  and STATUS_RANK (task status leaked into sprint components)

## Previously completed (sprints 30–35)

- completed `sprint-30-wire-dead-surfaces`
- wired Stop agent button; `PATCH /api/sprints/{id}` lifecycle transitions
  (planned→active→completed/cancelled); `started_at`/`completed_at` set on
  transition; `PATCH /api/tasks/{id}` for description and priority; sprint
  status badges and Start/Complete buttons in sprint view header
- completed `sprint-31-backlog-items`
- sprint creation with inline tasks; task cancellation; task dependency display;
  event log load-more with cursor; cancelled sprint filter in list and kanban
- completed `sprint-32-tier1-editing`
- task field editing in `TaskDetailDrawer` (title, type, criteria); sprint goal
  inline editing; activity panel auto-scroll via `useLayoutEffect`
- completed `sprint-33-tier2-gaps`
- workflow step badge on task cards and drawer; project creation from dashboard
  (`POST /api/projects`, `NewProjectModal`); `foreman run` from dashboard
  (`POST /api/projects/{id}/agent/start`, subprocess spawn, Run/Stop toggle)
- completed `sprint-34-task-edit-enforcement`
- `update_task_fields` tracks changed fields; `human.task_edited` event emitted
  for `in_progress`/`blocked` task edits; `getEventCategory` broadened to
  `human.*` prefix; synthetic run created when task has no run history
- completed `sprint-35-dashboard-crud-polish`
- board-view filter leak fixed (filters gated on list mode); delete task/sprint
  with FK-safe cascade in store; sprint title inline editing; sprint ordering
  (`order_index` in API, ↑/↓ reorder buttons); `started_at`/`completed_at`
  exposed in sprint responses; date display on cards and sprint header
- completed `sprint-36-intervention-and-ordering`
- sprint list ordering fixed: active/completed sprints above planned; stop
  individual task (`POST /api/tasks/{id}/stop`) with Stop button on cards and
  drawer; Cancel sprint button in sprint view header for active and planned
  sprints; board column equal-width fix; custom scrollbar styling; duplicate
  branch name generation fixed in orchestrator

## Previously completed (sprints 1–29)

- reconciled the previously loose feature and recovery histories into one
  integrated mainline and pushed the result to `origin/main`
- completed `sprint-14-dashboard-streaming-transport`
- added a dedicated dashboard sprint event stream with incremental persisted
  event delivery
- switched the dashboard activity panel to a live subscription path and
  debounced task-state refresh on incoming events
- completed `sprint-15-engine-db-discovery`
- added repo-local SQLite discovery using a hidden `.foreman.db` file
- made `foreman init` default to `<repo>/.foreman.db` while keeping `--db` as
  a deterministic override
- wired `projects`, `status`, monitoring commands, approve or deny, and the
  dashboard CLI entrypoint to use repo-local DB discovery without explicit
  flags
- updated scaffold generation so the default `.foreman.db` stays gitignored
- completed `sprint-16-security-review-workflow`
- added end-to-end orchestrator coverage for the shipped
  `development_secure` workflow variant
- covered security-review approval and denial transitions explicitly,
  including carry-output back into development after a denial
- documented how bootstrap project initialization should opt into
  `development_secure`
- completed `sprint-17-native-backend-preflight-checks`
- added explicit native backend preflight failure handling for missing Claude
  or Codex executables and malformed Codex startup responses
- made backend preflight failures fail once before `agent.started` instead of
  consuming infrastructure retries
- documented backend prerequisites and recovery expectations for operators
- completed `sprint-18-event-retention-pruning`
- added store-backed pruning of old project events by cutoff while preserving
  blocked and in-progress task history
- wired orchestrator startup to honor `event_retention_days` and emit
  `engine.event_pruned` when rows are removed
- documented retention boundaries, including the current schema constraint
  that pruning records still attach to a task-bound synthetic run
- completed `sprint-19-watch-live-tail-alignment`
- replaced bounded `foreman watch` snapshots with a persisted live tail for
  project, sprint, and run scopes
- aligned CLI watch delivery with the dashboard's cursor-based sprint-event
  model while keeping the CLI on a direct store-read transport
- documented the new watch boundary and advanced repo memory to the migration
  framework slice
- completed `sprint-20-production-hardening-reset`
- tightened repo instructions so bootstrap state now refers only to project
  memory and feature coverage, not to acceptable implementation quality
- accepted a dedicated web UI and API boundary that deprecates embedding the
  product dashboard inside one Python module
- recorded a ranked hardening detour for dashboard replacement, stub removal,
  migration work, and broader product-surface remediation
- completed `sprint-21-dashboard-api-extraction`
- extracted dashboard reads, task actions, and streaming payload assembly into
  what is now `foreman/dashboard_service.py`
- reduced the old `foreman/dashboard.py` module into a thinner HTTP adapter
  over the extracted backend contract while preserving the legacy dashboard
  shell during the transition
- strengthened dashboard regression coverage around API and SSE payload
  contracts to prepare the React handoff
- completed `sprint-22-dashboard-backend-foundation`
- replaced the raw dashboard stdlib server with a FastAPI backend in
  `foreman/dashboard_backend.py`
- switched `foreman dashboard` to a uvicorn-backed runtime while preserving
  the transitional dashboard shell and current JSON plus SSE routes
- added ASGI-backed dashboard HTTP tests so the backend is validated as a real
  app, not only as a service layer
- completed `sprint-23-react-dashboard-foundation`
- added a dedicated React and Vite frontend workspace in `frontend/` for the
  shipped dashboard surfaces
- removed the embedded dashboard HTML, CSS, and browser logic from Python and
  switched FastAPI to serve built frontend assets from
  `foreman/dashboard_frontend_dist/`
- added frontend component tests and bundle-build validation alongside the
  existing dashboard API and FastAPI regression suite
- pruned redundant dashboard transition checkpoint and PR-summary docs that no
  longer add repo-memory value after the React cutover
- clarified the live dashboard module split by renaming the runtime wrapper to
  `foreman/dashboard_runtime.py` and the service layer to
  `foreman/dashboard_service.py`
- added frontend-dev support to `foreman dashboard`, Vite `/api` proxying, and
  a one-command `npm --prefix frontend run dev:full` launcher for local
  dashboard work
- implemented the remaining shipped CLI product commands instead of routing
  them through `handle_stub`
- added real project, sprint, task, run, and config command behavior for the
  shipped CLI surface, including repo-local DB discovery support and stateful
  task or sprint transitions
- expanded CLI subprocess coverage to validate the hardened command surface
  end to end
- closed the most visible product-surface gaps after the dashboard frontend
  cutover
- added a settings panel, sprint creation, and task creation backed by real
  FastAPI endpoints and the dashboard service layer
- added `SettingsPanel`, `NewSprintModal`, and `NewTaskModal` React components
  wired into the dashboard app with validation and error handling
- strengthened product-surface validation with 15 new integration tests
  covering settings read/update, sprint creation, and task creation through
  both the service layer and FastAPI transport
- completed `sprint-25-migration-framework-bootstrap`
- replaced bootstrap DDL with a version-tracked migration framework in
  `foreman/migrations.py` and `foreman/store.py`
- `ForemanStore.initialize()` now creates a `schema_migrations` table and
  applies any unapplied migrations in version order; idempotent on repeat calls
- `ForemanStore.schema_version()` returns the highest applied migration version
- migration 1 is the current baseline schema; appending to `MIGRATIONS` is the
  only step required to add a schema change in future sprints
- 17 new tests in `tests/test_migrations.py` cover list integrity, fresh
  install, idempotency, incremental upgrade, and version tracking
- accepted `docs/adr/ADR-0005-schema-migration-strategy.md`
- completed `sprint-26-history-lifecycle-expansion`
- added migration 2 (`idx_runs_project_completed`) — `test_partial_db_upgraded_to_latest`
  now passes (was previously skipped)
- added `ForemanStore.prune_old_runs()`: hard-deletes terminal runs and their
  cascaded events older than a cutoff; protects blocked/in-progress task runs
- added `ForemanStore.strip_old_run_prompts()`: nulls `prompt_text` on old
  terminal runs without deleting the run record or its telemetry
- expanded orchestrator startup pruning via `prune_old_history()` which reads
  `run_retention_days` and `prompt_retention_days` from project settings
  alongside the existing `event_retention_days`; emits `engine.run_pruned` and
  `engine.prompt_stripped` lifecycle events
- 19 new tests in `tests/test_run_retention.py`; 188 tests pass total
- completed `sprint-27-e2e-dashboard-validation`
- installed `playwright` and `pytest-playwright`; Chromium browser binaries available
- added `tests/test_e2e.py` with 20 Playwright E2E tests driven against a real
  uvicorn dashboard server and seeded SQLite database; covers dashboard load,
  project/sprint navigation, task detail drawer, settings panel, sprint
  creation, and task creation end to end
- E2E tests skip gracefully when Playwright is not installed
- 208 tests pass total (20 new E2E + 188 prior)
- completed `sprint-28-autonomous-task-selection`
- implemented `task_selection_mode="autonomous"` in `ForemanOrchestrator`:
  `select_next_task()` dispatches to `_select_next_task_autonomous()` which
  resumes in-progress tasks first, then creates placeholder tasks up to a
  per-sprint `max_autonomous_tasks` limit (default 5, configurable via project
  settings)
- the placeholder task (`created_by="orchestrator"`, `title="[autonomous] new
  task"`) is persisted to SQLite; the agent populates it via the existing
  `signal.task_started` handler
- 8 new tests in `AutonomousTaskSelectionTests`; 204 non-E2E tests pass total
- completed `sprint-29-db-migrate-cli`
- added `foreman db version` — reports current schema version; warns when
  `schema_migrations` table is absent (pre-migration-framework databases)
- added `foreman db migrate` — calls `store.initialize()` (idempotent); reports
  each applied migration with version number and description, or confirms the
  schema is already up to date
- changed `ForemanStore.initialize()` to return `list[int]` (applied migration
  versions); backward-compatible since callers ignored the prior `None` return
- 7 new tests in `DbCommandTests`; 203 non-E2E tests pass total
- completed `sprint-31-backlog-items`
- sprint creation modal now accepts inline task entries; tasks are created
  atomically with the sprint via `initial_tasks` in the API body
- task cancellation: `POST /api/tasks/{id}/cancel` + Cancel task button in the
  detail drawer; rejects done/already-cancelled tasks with 400
- task dependencies: `depends_on_task_ids` now included in `get_task()` response;
  detail drawer renders a Dependencies section with chips
- event log load-more: `before_event_id` cursor in store and service; `has_more`
  flag on all `list_sprint_events` responses; "Load older events" button in UI
- cancelled sprint filter: added to `STATUS_FILTER_OPTIONS`; kanban Done column
  includes cancelled sprints
- 8 new tests in `DashboardSprintTaskBacklogTests`; 221 non-E2E, 20 E2E tests
- completed `sprint-30-wire-dead-surfaces`
- wired `Stop agent` button to `POST /api/projects/{id}/agent/stop`; blocks all
  in-progress tasks in the active sprint and emits `human.stop_requested` events
- added `PATCH /api/sprints/{sprint_id}` endpoint with valid lifecycle transitions
  (planned→active, active→completed/cancelled); sets `started_at`/`completed_at`
- added `PATCH /api/tasks/{task_id}` endpoint for `description` and `priority`
  field updates; unknown fields rejected with 400
- extended run serialization in `get_task()` to include `session_id`,
  `branch_name`, `started_at`, `completed_at`
- exposed `description` and `priority` in `get_task()` and `list_sprint_tasks()`
  responses; task detail drawer shows both when non-default
- added sprint status badge + Start/Complete sprint buttons to sprint view header
- added Start/Complete/Cancel action buttons to sprint list cards
- fixed two E2E test regressions from previous dashboard overhaul session
- 10 new tests in `DashboardSprintLifecycleTests`; 213 non-E2E, 20 E2E tests pass

## Current repo state (as of sprint-41)

- The repository now contains:
  - the product spec and UI mockup,
  - the `foreman` package with SQLite-backed models, store, loaders, CLI, and
    orchestrator,
  - runtime `.foreman/context.md` and `.foreman/status.md` projection from
    SQLite,
  - repo-local `.foreman.db` discovery for normal CLI usage with `--db` still
    available as an explicit override,
  - persisted human-gate approval and denial commands with deferred or
    immediate native resume behavior,
  - the opt-in `development_secure` workflow executing code review, security
    review, test, and merge with durable transition state,
  - native Claude Code and Codex runners with structured event capture,
    explicit startup preflight checks, approval-policy handling, retry
    normalization, and persisted session reuse across fresh orchestrator
    invocations for persistent roles,
  - orchestrator startup event-retention pruning driven by
    `event_retention_days`, with durable `engine.event_pruned` records and
    protection for blocked and in-progress task history,
  - monitoring CLI surfaces for board, history, cost, and live watch tails
    across project, sprint, and run scopes,
  - accepted ADRs for runner session semantics, dashboard data access, the
    dedicated product web UI boundary, and the FastAPI dashboard backend
    framework,
  - a dashboard service layer in `foreman/dashboard_service.py` covering
    project, sprint, task, action, and incremental streaming payloads,
  - a FastAPI transport layer in `foreman/dashboard_backend.py` that serves
    the current dashboard routes, built frontend shell, and SSE stream through
    an actual ASGI app,
  - a dedicated React dashboard frontend in `frontend/` plus built assets in
    `foreman/dashboard_frontend_dist/`,
  - queue-oriented sprint management with Active, Queue, and Archive sections,
    plus sprint advancement that now respects project `autonomy_level`,
  - decision gates plus dashboard banners and resolution actions for
    sequencing conflicts,
  - a per-project meta-agent sidebar backed by a persistent Claude Code
    subprocess with streamed text and tool-use events,
  - `foreman/dashboard_runtime.py` as the asset-aware uvicorn entrypoint for
    `foreman dashboard`, with an explicit frontend-dev mode that no longer
    requires built assets,
  - `frontend/vite.config.js` proxying `/api` to the local FastAPI backend and
    `scripts/dashboard_dev.py` providing a one-command frontend plus backend
    dev loop,
  - unit and integration coverage across store, CLI, orchestrator, runners,
    dashboard, the React frontend, scaffold, and executor seams,
  - a version-tracked schema migration framework (`foreman/migrations.py`,
    `schema_migrations` table, `ForemanStore.migrate()`,
    `ForemanStore.schema_version()`),
  - run and prompt retention via `ForemanStore.prune_old_runs()` and
    `ForemanStore.strip_old_run_prompts()`, wired into orchestrator startup
    via `prune_old_history()`,
  - 20 browser-driven E2E tests in `tests/test_e2e.py` covering the full
    FastAPI + SQLite + React dashboard stack via Playwright and Chromium,
  - full dashboard CRUD: create, edit, and delete for projects, sprints, and
    tasks; sprint title and goal inline editing; sprint ordering via ↑/↓ with
    `order_index` in all sprint API responses; `started_at`/`completed_at`
    displayed on sprint cards and in sprint view header,
  - `human.task_edited` event emission for in-progress and blocked task edits,
    with synthetic run creation when no run history exists,
  - 95 dashboard unit/integration tests and 20 E2E tests all passing,
  - repo-memory docs that are intended to let a fresh agent continue from the
    next slice without reconstructing prior branch history.
- The temporary markdown sprint and status workflow remains intentional
  bootstrap state. The eventual product should move operational state into
  SQLite as described in the spec.

## Ready next

- SSE transport hardening (Tier 3, deferred — documented architecture gap)
- E2E test coverage for sprints 32–35 features
- E2E test coverage for the meta-agent panel
- Persist meta-agent session history to SQLite
- Task `order_index` editing UI within the sprint board
- Task priority editing UI
- Move task between sprints
- Codex cost capture
- Run and prompt retention product-level defaults
- See `docs/sprints/backlog.md` for full list

## Open risks

- Repo-local discovery currently depends on an existing `.foreman.db` in the
  current repo lineage or on `foreman init` creating one; cross-repo and
  out-of-repo inspection still requires explicit `--db`.
- the committed dashboard build output in `foreman/dashboard_frontend_dist/`
  must stay in sync with the source app in `frontend/`; E2E tests will fail
  if the build is stale.
- the sprint SSE path still polls SQLite directly inside the FastAPI stream
  loop; that is acceptable for now, but it is not a final transport design.
- file-backed stores run in WAL mode, which needs a local filesystem; on
  media where the pragma fails the store silently keeps the rollback journal,
  and `.foreman.db-wal` / `-shm` sidecars appear next to the database.
- event, run, and prompt retention are opt-in; audit-grade events are not yet
  separated from telemetry, so enabling retention prunes both.
- Native backend preflight now validates executable presence and Codex startup
  handshake assumptions, but it does not yet prove downstream auth or service
  reachability beyond startup.
- The Codex app-server protocol exposes token usage but not USD pricing, so
  Codex runs currently persist `token_count` accurately while `cost_usd`
  remains `0.0`.
- `task_selection_mode="autonomous"` is now implemented; the agent must emit
  `signal.task_started` to populate placeholder tasks or they remain with the
  default title.
- Run and prompt retention are controlled by optional project settings; if neither `run_retention_days` nor `prompt_retention_days` is set, old runs and prompts accumulate indefinitely.
- The migration framework covers DDL changes but does not yet provide a down/rollback path; adding that is deferred until a rollback scenario is observed in practice.
- project-scoped `foreman watch` resolves the active sprint once at startup;
  if sprint ownership changes mid-tail, operators currently need to restart
  the command to follow the new sprint.
- dashboard validation now covers the extracted service layer, FastAPI
  delivery, React component behavior, and browser-driven E2E flows via
  Playwright and Chromium.

## Documented conflicts

- The spec's shipped workflows (`docs/specs/engine-design-v3.md` §5) run code
  review before the test built-in. Since sprint 53 slice 4 every shipped
  workflow tests first and gates the merge behind a policy-governed
  `merge_approval` human gate, because reviewers should judge with real test
  results and a merge authorization must be a policy decision. The spec text
  has not been revised yet.
- The shipped workflow TOML treats `_builtin:mark_done` as a terminal step with
  no outbound transition, while the orchestrator pseudocode in the spec blocks
  any missing transition. The current implementation treats a step that sets
  task status to `done` as successful workflow termination and records that
  nuance here until the spec text is clarified.
- The spec's CLI examples omit explicit database selection and do not define a
  bootstrap discovery path. The current runtime defaults to repo-local
  `.foreman.db` discovery for normal flows and keeps `--db PATH` as an
  explicit override until engine-instance configuration exists.
- The spec expects `.foreman/status.md` to list open decisions, but the current
  SQLite schema has no structured decision records yet. The runtime projection
  currently emits an explicit placeholder until those records exist.
- The mockup is a static HTML interaction reference, not a frontend stack
  specification. The previous implementation treated that as enough license to
  embed the dashboard directly into a Python module; the active architecture
  direction now rejects that interpretation, and the shipped dashboard now
  follows the React plus FastAPI split.
- The spec describes `foreman approve` and `foreman deny` as immediately
  resuming workflow execution. The current runtime does that when the next
  backend and repo are available, but it still persists a deferred next step
  when the resumed workflow cannot execute safely yet.
- The spec's retry pseudocode retries every `InfrastructureError`. The current
  runtime now treats backend preflight failures as explicit non-retryable
  startup errors so missing executables or malformed startup handshakes fail
  once before `agent.started`.
- The spec describes `engine.event_pruned` as a project-level emit, but the
  current schema still requires non-null `run_id` and `task_id` on events. The
  runtime therefore records pruning through a synthetic orchestrator run
  attached to one stable project task.
- ADR-0007 describes a restricted sprint-planner session that manages
  sprint and task state through Foreman APIs only. The shipped `meta_agent.py`
  instead launches a full-access Claude Code repo session with git, CLI, and
  file-system access plus in-memory history. Treat the ADR as not yet aligned
  to the shipped surface.

## Open decisions

- whether the repo-local `.foreman.db` location should remain long-term or
  give way to a broader engine-instance configuration model
- whether project `default_model` should be validated against the selected
  backend instead of being passed through verbatim at runtime
- whether backend preflight should eventually expand beyond executable and
  startup-contract checks into authentication or service reachability checks
- whether run and prompt retention thresholds should have product-level defaults rather than requiring explicit project settings
- whether the secure workflow should remain an explicit opt-in at init time or
  be selected automatically from project policy in a later slice
- whether project-scoped watch should eventually auto-rebind if a different
  sprint becomes active during a long-lived tail session
