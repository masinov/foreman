# Production readiness review

- Date: 2026-09-03, revised the same day after the goal was clarified
- Baseline: `main` at `dfba0a6`
- Goal under review: a robust, auditable, configurable-autonomy harness where
  tasks arrive from people and other systems, the engine implements and the
  machine verifies them, and humans intervene only where policy requires,
  with a chat reachable without a terminal.

This is the repo-memory version of the review that drives sprints 53 and
onward. It records the verdict, the defects, the target shape, and the
roadmap. Findings were produced by direct reading of the orchestrator,
built-ins, evidence builder, judge, git helpers, context projection, roles and
workflows, plus three independent reviews of the runner layer, the store and
concurrency layer, and the dashboard, manager, and frontend. Every critical
and high finding was re-checked against the source; the foreign-key crash and
the duplicate task key were reproduced against a fresh database.

## Verdict

Keep the engine, replace the edges, add the intake.

Worth keeping as built: SQLite as source of truth with an append-only event
log, declarative roles and workflows, the step loop with loop limits and cost
and time gates, session persistence for the developer role, tiered review with
a curated diff payload, persisted human gates and decisions, attention events
for human-by-exception, autonomy levels and decision gates as the seed of a
policy layer, and the service-behind-transport dashboard split.

Not ready: everything that touches the outside world. Inbound, nothing can
hand Foreman work safely (task creation needs a sprint, no API auth or
idempotency, the engine exits when idle). Outbound, integration merges into a
local default branch in the operator's checkout, so there is no pull request,
no CI, and no record of who authorized what. In between, agents run
unsandboxed in that checkout, a hung agent hangs the engine, a Stop does not
unwind, the proof gate is a keyword-overlap score, and the dashboard and its
chat have no login.

## Pipeline coverage

| Stage | Status | Gap |
|---|---|---|
| Intake | missing | no project-level endpoint, no API auth, no idempotency, no resident engine |
| Plan | partial | no per-task planning step; in autonomous mode the implementer authors its own criteria; chat unsafe |
| Execute | partial | no worktree or container isolation, no parallelism, unreliable timeouts and cleanup |
| Machine verify | partial | tests run after review; score rewards file count and keyword overlap; no CI, lint, or type gates; no test timeout |
| Human verify | missing | gate placement fixed in workflow, no per-task policy, no identity, no notification |
| Integrate | missing | local merge, nothing pushed, no PR, no branch protection |
| Operate | missing | no auth, no logging, engine output discarded, registry lost on restart, chat unsandboxed |

## Defects, ordered by severity

| Sev | Where | What happens | Fix |
|---|---|---|---|
| critical | `store.py prune_old_runs`, migration 7 | run pruning violates the FK from gate decisions once one approval exists; runs at every engine start | cascade / set-null migration, dependent-aware deletes (sprint 53 slice 1) |
| critical | `runner/claude_code.py:116`, `runner/codex.py:410` | blocking stdout read; time and cost gates fire only after a parsed event; hung agent hangs the engine | reader thread with wall-clock gates (slice 2) |
| critical | `runner/claude_code.py:397`, no signal handlers | kill hits only the direct child; no process group; no SIGTERM/atexit cleanup | process groups, group kill, cleanup registry (slice 2) |
| critical | `dashboard_backend.py:106`, `meta_agent.py:207` | no auth, wildcard CORS, manager session with `bypassPermissions` in any `repo_path` | auth, no wildcard CORS, allowlisted repos, sandboxed manager (slice 5, Phase 1) |
| high | `cli.py handle_run` | engine is one-shot and exits when idle | resident `foreman serve` worker (Phase 1) |
| high | `orchestrator.py _run_is_stale`, `leases.py` | a run quiet for five minutes can be taken over by a second engine; fencing token never checked | project-level engine lock with timer heartbeat (Phase 1) |
| high | `runner/claude_code.py:215, 265` | signals parsed from assistant blocks and again from the result; duplicate tasks | parse once, dedupe (slice 3) |
| high | `orchestrator.py _contains_completion_marker`, `_extract_decision_output` | whole transcript scanned; last decision-shaped line wins | final message only, ambiguity is `error` (slice 3) |
| high | `runner/base.py run_with_retry` | infrastructure retry replays without the session id after commits | session-aware replay (Phase 1) |
| high | `runner/claude_code.py:80`, `runner/codex.py:341` | stderr never drained; deadlock past 64 KiB | drain on a thread (slice 2) |
| high | `dashboard_service.py:34, 880` | process registry is a module dict; Stop flips tasks to blocked while the engine continues | engine registry in the database, graceful stop (Phase 1) |
| high | `store.py:280` | rollback journal, no WAL, no lock handling across three processes | WAL, busy timeout, retries (slice 1) |
| high | `store.py migrate` | `executescript` half-applies; drift-repair patches the symptom | atomic per-migration transactions (slice 1) |
| high | migration indexes | `events(task_id)` unindexed; every SSE tick scans | index (slice 1) |
| high | `runner/claude_code.py:116`, `builtins.py run_tests` | every raw stream line persisted unredacted; DB inside the repo | cap and redact, move DB (Phase 1) |
| high | `workflows/*.toml` | review before test in every workflow | develop, test, review, merge (slice 4) |
| high | `builtins.py run_tests` | no timeout on the test command | timeout (slice 2) |
| high | `store.py get_latest_session_id` | session key ignores model and endpoint; stale id never cleared | key on model and env, invalidate on failure (Phase 1) |
| medium | `dashboard_service.py create_task` | task creation needs a sprint; no auth, idempotency, or source | intake endpoint (Phase 1) |
| medium | `orchestrator.py _apply_agent_signal` | agent-created tasks run without policy; any role can emit | per-role allowlist, intake path (slice 3, Phase 1) |
| medium | `store.py _next_task_key` | scan-based key allocation; two writers mint the same key | per-project sequence in the insert transaction (slice 1) |
| medium | `orchestrator.py`, `settings.py` | orchestrator reads raw settings; validated defaults never apply | `ProjectSettings` at run start and every write (slice 1) |
| medium | `frontend/src/App.jsx:134` | stale response overwrites newer view; stream reconnect drops events | request tokens, stable effect deps (Phase 1) |
| medium | `dashboard_backend.py:292` | stream stalls after a full batch until the next commit | loop until a short batch (Phase 1) |
| low | `pyproject.toml` | unused `anthropic` dependency | drop (slice 6) |

## Target shape

- **Autonomy as policy, not a mode.** Project defaults, task-type rules, and
  per-task overrides answer "machine or human?" at intake, plan, execute,
  merge, and exception. The per-task override mechanism for models is the
  pattern; decision gates and gate decisions are the state.
- **Intake from anywhere.** One project-level endpoint, token-authenticated,
  idempotent on an external reference, carrying source metadata, landing in a
  policy-chosen status. Sprints become optional grouping over a continuous
  queue.
- **Planner separate from implementer.** A planner step authors criteria and
  a protected acceptance test before any developer step; the agent that
  implements never writes the criteria it is judged by.
- **Isolate every task.** A git worktree per task in a Foreman-owned
  directory, later a container.
- **Integrate through pull requests.** Push, open PR with the evidence, wait
  for CI and the approvals policy requires, merge through the remote.
- **Verify with facts.** Deterministic checks, then the LLM judge and
  reviewers who see test results, then a human where policy says. No numeric
  score.
- **Engine as a service.** `foreman serve` with a project lock, SIGTERM
  handling, structured logs, a command table, and a dead-letter state.
- **A name on everything.** Login, API tokens, actor columns, notifications.
- **Chat as a first-class surface.** Launched through the runner with a
  declared tool set, per-user sessions, kill on disconnect, cost per turn.

## Roadmap

1. **Phase 0, sprint 53 (about two weeks):** store safety; runner process
   lifecycle; output contract and signals; workflow order and merge gate;
   dashboard minimum safety; cleanup. See `docs/sprints/current.md`.
2. **Phase 1, unattended pilot (six to eight weeks):** resident worker;
   intake endpoint; policy matrix v1; planner step; worktree per task;
   pull-request integration; facts-based verification with the judge on by
   default; login, identity, notifications; chat hardened; session key on
   model and endpoint; atomic migrations as a deploy step; database out of
   the repo; frontend split and CI-built bundle.
3. **Phase 2, scale:** parallel workers and containers; planner-driven
   backlog; reply-to-chat from notifications; multi-repository projects; a
   price table for third-party endpoints; stream pub/sub; Codex promoted
   only after a real-binary smoke test.

## Remove or replace

Remove: the bootstrap supervisor scripts; the numeric evidence score and
verdict ladder; the schema drift-repair helper once migrations are atomic; the
unused `anthropic` dependency; the developer-authored task contract once the
planner step exists.

Replace: per-task leases with one engine lock until parallel workers arrive;
the local merge built-in with pull requests; the one-shot engine with a
resident worker; the in-memory process registry with an engine table; the
single autonomy setting with a policy matrix; mandatory sprints with optional
grouping over a queue; hardcoded reviewer role ids with outcomes declared in
the role file.
