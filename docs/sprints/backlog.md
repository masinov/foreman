# Backlog

## Owner decisions, 2026-11-19: the manager and people (roadmap stage 2)

Settled in discussion with the owner on 2026-11-19. Stage 2 of
`docs/ROADMAP.md` builds them, after an ADR.

- **Work is registered.** Everything done through Foreman is listed and
  auditable; no task or feature is developed without being listed. The
  record is kept whole where code enters `main` (only Foreman's merge moves
  it), not by limiting sessions.
- **Identity.** Foreman gets a simple identity system of its own, which a
  company-wide one can replace later. This supersedes the 2026-11-16 line
  "no login, user or role-of-person work until the owner asks".
- **The manager** is the project lead and the person's way of operating
  Foreman. It sees everything and investigates freely (scripts, queries,
  tests run against `main`). It acts directly when a person asks, recorded
  under that person's name; a plan of several tasks is shown before it is
  applied. It writes no code that goes into the product: code comes only
  from tasks. It can adjust how a task is done: per-task model and policy
  overrides, notes to the developer and reviewers, the workflow before the
  task starts, engine control. The FOR-42 write limit (ADR-0022 amendment)
  is revisited with it.
- **One manager conversation per person per project.** What it does lands in
  the project's shared activity. There is no conversation owned by no one.
- **Roles:** owner (at least one per project; controls everything in it) and
  member. A client is a task's reporter, not a user.
- **Two decisions per task:** who is responsible, and whether it is accepted
  (or declined, or changed in type and accepted). They are independent: a
  ticket can name its responsible person and still be declined by them. A
  task runs only when it is accepted and has a responsible person.
  - A member filing their own work: responsible and accepted at once.
  - A member may file work for others to pick up; they are its reporter.
  - An owner may assign anyone; the person is notified.
  - A task with nobody responsible: any member or owner decides; whoever
    accepts it becomes responsible, unless an owner names someone.
  - A task from an external system waits; a connector may name the
    responsible person when that person is in the project.
  - Derived work (an agent's follow-up, a split) inherits the responsible
    person of the work it came from.
  - A person's manager acts as that person, with their rights.
- **Handing over:** offered and accepted between members; an owner reassigns
  directly; a person who leaves the project hands back to the owners.
- **Notices** go to the responsible person and always to owners, who also
  see what is waiting, on whom and since when, and can act.
- **Conflicts:** a change to someone else's work is a request to its
  responsible person or an owner (the proposal card, used for this). A
  change based on an out-of-date task is refused, saying what changed and
  by whom. Code conflicts stay with the merge.
- **Permissions:** a worker's freedom depends on the machine and what it can
  reach. Gates sit at the boundaries (entering `main`, shared or production
  resources, deploying) as policies with defaults a project can change.
- **Deferred:** decisions sent back to a ticketing app (owner: "let's not try
  to close absolutely everything right now").

## Owner directions, 2026-11-18: after sprint 60 and the base work

Recorded so they are not lost. Each one gets an ADR before any code. Sprint
60 and the remaining base work come first. Feature 1 is the next line of
work after that.

What they serve: Foreman as a software factory and a meta-harness. It
coordinates several harnesses and models, each with its own strengths and
prices. Its many thin arms work through existing tools (CI/CD, clusters,
trackers, identity) rather than rebuilding them. Before each arm's ADR,
survey the existing tools.

Base work that this framing makes necessary:

- **Outcome numbers per project, model and role:** first-pass success,
  send-backs, interventions by a person, and cost per merged task. These
  show whether routing between models pays.
- **Codex as a real second harness:** a smoke test against the real
  program, its cost recorded, and the same kind of task run through both
  harnesses.

1. **One central Foreman server, with workers on other machines.**
   - A worker program on each machine connects out to the server, keeps a
     clone per project and a working copy per task, and runs agent and test
     steps there. It streams events back and pushes the task's branch.
   - A project or step names a machine, or states requirements such as OS
     and installed software. A task stays on the machine that holds its
     agent session.
   - The setting is multi-user and multi-project, and identity is needed.
   - First case: a BricsCAD MCP server developed on a Windows machine.
2. **Shared compute, through a cluster manager, only when configured.**
   Foreman does not manage shared GPUs and CPUs: the company's people use
   them too. A project can point Foreman at a cluster manager, such as Ray,
   and a task's agent or a workflow step then submits jobs with resource
   requests. Foreman records each job on the task (waiting, where, how
   long, log, result) and enforces limits on it.
3. **Releases and deployment, through existing CI/CD.** Foreman does not
   build or deploy. It decides when a version is cut, under a policy gate
   such as merge approval. It starts the CI/CD pipeline (GitLab CI, GitHub
   Actions, and so on), follows it, and shows its stages, artifacts and
   environments on the sprint. It reacts to a failure. The same connector
   reads CI checks on a task's branch, which is the pull-request
   integration of Phase 5. A release can be code, an image or a trained
   model; in each case Foreman records where it came from.
4. **Workflows above the task: a sprint workflow (owner's question,
   2026-11-18; leads into 3).**
   - **Today:** workflows are per task only. A sprint's life is fixed in
     code (`foreman/engine/sprints.py`, ADR-0025): activated, its tasks run,
     finished by a person or by the engine. A run must belong to a task.
   - **The idea:** a declarative sprint workflow with steps before its tasks
     (plan, plan gate) and after them. After them come checks on the
     integrated `main`, a release gate, the release pipeline, its
     observation, and notes.
   - **The loop it allows:** a failing sprint-level check files fix tasks
     into the same sprint, and the sprint runs again until its checks pass.
     No task workflow can express that.
   - **Global roles (owner, 2026-11-18):** roles triggered at the end of a
     sprint that look at the whole sprint, not at one task. This is where a
     judge of the sprint's acceptance belongs; the per-task criteria judge
     was removed (ADR-0010 amendment).
   - **Further out:** recurring and event-triggered loops at project level,
     which create tasks or sprints and stop there.

## Carried engineering items (from sprints 56 and 57)

- `resume_human_gate` and `_run_leased_task` are still on the orchestrator;
  the agent step's corrective retry repeats its first attempt.
- The lease fencing token is unchecked on writes.
- A stale `running` agent run is reset to the entry step, not resumed in
  place.
- `--json` on the remaining read commands; response models on the API.
- Python `Enum` classes for statuses.

## Found while Foreman built sprint 58 (2026-11-12 and 13)

Engine and workflow defects seen while the engine ran sprint 58's tasks.
All were fixed in sprint 59.

- (Fixed in sprint 59, slice 1.) A corrective retry that ended with zero
  turns counted as a second failure.
- (Fixed in sprint 59, slice 2.) A resumed session's cost was recorded
  cumulatively on each run, so a task's spend was overcounted.
- (Fixed in sprint 59, slice 3.) `foreman engine run-task` only took effect
  at the engine's next pass, which came after the whole queue had run.
- (Fixed in sprint 59, slice 4.) Merges were only attempted between tasks,
  so an approved merge could wait behind a long step of another task.
- (Fixed in sprint 59, slice 5.) The engine did not push after a merge; it
  does when `merge_push_remote` names a remote.
- (Fixed in sprint 59, slice 6.) The reviewer approved a 1,310-line change
  in seven seconds without opening a file. An approval of a cut diff with no
  file opened is now sent back once and then stops the task.
- Two branches that both rebuilt the committed bundle conflicted every time
  (resolved: the bundle is no longer in git).

## Found in the supervised run of sprint 60 (2026-11-16)

Fixed in the second run of the same day (ADR-0025, ADR-0026, the Python rule).
Left: a completed sprint cannot be reopened (`foreman sprint activate`
refuses).

## After ADR-0028 (Foreman starts backlog work)

- A limit per day for a project that keeps one standing sprint fed by intake;
  per sprint never resets there.
- A cap on how many tasks one agent step may file, and refusing a filing that
  repeats an open or declined one.
- Show, on a task an agent filed, which task the agent was working on.
- `autonomy_level` (who finishes a sprint, ADR-0025) has no control in the
  dashboard; it is set from a terminal.
- Trust per access token for work filed by other systems.

## Found in the audit of every screen (2026-11-16)

- Acceptance criteria are never judged unless a project sets `judge_model`
  and `judge_base_url`, which no page offers; every finished task says "not
  judged yet", while the Workflow tab lists "Acceptance criteria marked met"
  as something finishing requires.
- The board of a finished sprint is one long Done column and leaves out
  cancelled tasks.
- "Developer (worker fleet)" is a shipped role no workflow uses.
- The test command and the other "This machine" values can only be changed
  from a terminal.
- `foreman role|workflow set` cannot change a workspace default; `foreman
  init` and the Runners list read the shipped files only.

## Dashboard follow-ups (after sprint 58)

- (Done in sprint 59, slice 9.) A task's Activity tab showed run events as
  raw JSON; they are said in sentences.
- A browser acceptance pack for the operator journeys (inspect and guide a
  running task, approve a merge, pause, recover from an engine failure).
- Types in the frontend (TypeScript or JSDoc).
- Descriptions and manager replies rendered as markdown.
- (Done in sprint 59, slice 11.) Mark done and Reopen in the manager's
  proposal vocabulary (ADR-0022).
- Look at the task and sprint pages against a running engine: everything
  built after 2026-11-13 was seen with fixtures only.
- (Done in sprint 59, slice 10.) Editing a task's size, priority and
  dependencies after it is filed.
- Motion that depends on live data (a row arriving, a step finishing).
- One event stream per tab instead of two on a running task's page.
- (Done in sprint 59, slice 8.) FOR-42: restrict the manager session's tools
  to the read surface.
- FOR-43: the proposal card's "Then" row for a send-back, and a summary line
  for earlier proposals.

## Finish plan — `docs/reviews/2026-11-10-full-review-and-finish-plan.md`

The 2026-11-10 review is the forward roadmap and supersedes the ordering of
the Phase 1 and Phase 2 lists below where they overlap. Sprint 55 covers its
Phases 0 and 1. Queued after that, in order:

- **Phase 2, engine truthfulness:** column-scoped task updates and a status
  re-read before each step; try/finally around every step with the next step
  persisted in the same write; worktree checks in place of the default-branch
  assertion; facts-based evidence tied to the head commit; session-aware
  retry and structured quota detection; durable engine commands; triage
  events through the notification dispatcher; guidance delivered to the agent
  or relabelled as a note; enums with CHECK constraints; one settings object.
- **Phase 3, structure:** `foreman/engine/`, `foreman/store/` and
  `foreman/cli/` packages; one task and sprint mutation service shared by CLI
  and dashboard; routers, request models, one error envelope and `/api/v1`;
  roles, workflows and templates as package data; test suite split with
  shared fixtures.
- **Phase 4, frontend rebuild:** design reference agreed first; primitives
  (dialog, slide-over, field, button, menu); per-scope data hooks with stale
  guards; task page with the pending decision first; settings as sections
  with one autonomy model; readable activity; browser acceptance tests;
  ESLint.
- **Phase 5, finish the product:** planner step per task; pull-request
  integration; login and roles as a pluggable seam (no provider chosen);
  agent sandbox (first cut done in sprint 59; a container per task is
  left); manager chat through the runner; spec §6.4 checkpoints;
  Codex role and smoke test; database out of the repository; deployment
  guide.

## Production readiness roadmap — `docs/reviews/production-readiness-review.md`

The readiness review is the forward roadmap. Phase 0 shipped as sprint 53
(archived at `docs/sprints/archive/sprint-53-phase0-unattended-safety.md`).
Phases 1 and 2 are queued here in order; sprint 54 opens Phase 1.

### Phase 1 — unattended pilot (sprint 54 onward)

- `foreman serve` resident worker: project lock, SIGTERM handling, structured
  logging, a command table the dashboard writes to, dead-letter state for
  tasks that exhaust their retry budget. **Sprint 54, slices 1–2.**
- Intake endpoint: project-level, API-token authenticated, idempotent on an
  external reference, source metadata, policy-chosen initial status
  (`triage` or `todo`); sprints optional over a continuous queue.
  **Sprint 54, slice 3.**
- Policy matrix v1: project defaults, task-type rules, per-task overrides for
  triage, plan approval, merge authorization, and notification.
  **Sprint 54, slice 4.**
- Planner step per task producing criteria and a protected acceptance test;
  the architect role repurposed from once-per-sprint to once-per-task.
  **Sprint 54, slice 5.**
- Worktree per task under a Foreman-owned directory; remove
  operator-checkout assumptions. **Sprint 54, slice 6.**
- Pull-request integration (GitHub via `gh`, decided at sprint 54 open):
  push, open PR with evidence, watch checks and approvals, auto-merge or
  wait per policy, mark done on merge; waivers as labels. **Sprint 55.**
- Facts-based verification: the numeric score and verdict ladder are gone
  (sprint 56 slice 8, ADR-0018). Still open: LLM judge on by default,
  acceptance tests in a protected path.
- Login and actor identity; Slack or email on attention events and waiting
  gates.
- Manager chat hardened: per-user sessions, turn lock, kill on disconnect,
  runner-launched with a declared tool set, cost per turn.
- Session key on model and endpoint; invalidate on resume failure;
  session-aware infrastructure retry.
- Migrations run as a deploy step; ledger the task-key backfill; retire
  `_repair_known_schema_drift`.
- Database moved out of the repository directory; raw output capped and
  redacted into its own table; audit-grade events split from telemetry
  before retention is enabled by default.
- Frontend split by view; bundle built in CI; navigation race and stream
  reconnect fixed; SSE batch stall fixed.

### Phase 2 — scale and full autonomy

- Parallel workers across worktrees; container execution; per-task leases
  return for parallelism.
- Planner-driven backlog from the spec and agent-discovered follow-ups,
  accepted automatically where policy allows.
- Reply-to-chat from Slack or email notifications.
- Multi-repository projects and per-repository settings; a price table for
  third-party endpoints; per-day budgets per project.
- In-process pub/sub for the stream; cost and throughput dashboards.
- Codex promoted from experimental only after a real-binary smoke test and
  cost reporting.

## Review roadmap from `docs/specs/review.md` — COMPLETE

The deep backend review was the forward implementation roadmap. **All phases
(0–7) are now merged to `main`** (top at `35b667c`, 2026-06-13) and the sprints
are archived under `docs/sprints/archive/`. The per-sprint entries below are
retained for traceability; none are pending. The only open item from the
roadmap is the deferred tool-enabled re-review follow-up (see Sprint 51 note).

### Sprint 47 — review Phase 0 correctness

Fix the remaining Phase 0 bugs with regression tests:

- `signal.task_created` must persist `engine.task_created` against the active
  run.
- `foreman waive-merge` must import and exercise `uuid4`.
- dashboard human/stop events must always reference a real run id.
- dashboard Run/Stop process registry must survive request boundaries and
  terminate spawned `foreman run` processes.
- completion evidence should only be built for decision roles and should be
  invalidated when branch head changes.
- dashboard cancellation should clear stale workflow resume state.
- remove the dead `foreman/executor.py` path.

### Sprint 48 — review Phase 1 multi-model fleet

Add per-role `[agent.env]` resolution, runner env plumbing, endpoint session
isolation docs, token-accounting visibility for zero-cost token runs, and the
`developer_worker` example role.

### Sprint 49 — review Phase 2 manager hardening (implemented on `feat/meta-agent-persistence`)

Persist meta-agent sessions and turns, rebuild compact state on every turn,
make the manager contract honest through CLI gaps, and preserve chat history
across dashboard restarts.

Done: migration 11 (`meta_sessions`/`meta_turns`), store-backed `meta_agent`
with crash-safe turn persistence, `build_state_header`/`build_operating_contract`,
`meta_agent_model` setting, paginated `meta/history`, and `foreman task add`
`--description`/`--sprint`/`--depends-on`. Merged to `main` at `62c2e25`;
archived at `archive/sprint-49-meta-agent-persistence.md`.

### Sprint 50 — review Phase 3 executor overrides and escalation ladder (implemented on `feat/executor-overrides-ladder`)

Add task executor overrides, task complexity, role `model_ladder`, deterministic
model resolution, `workflow.model_selected` events, CLI/API override surfaces,
and architect-created complexity persistence.

Done: migration 12, `Task.executor_overrides`/`complexity`, role
`model_ladder`, `resolve_step_model` wired into the workflow loop + native
runner with `workflow.model_selected` events, `signal.task_created` complexity
persistence, `foreman task add --complexity`, `foreman task override`, and
validated `executor_overrides` on `PATCH /api/tasks/{id}`. Merged to `main` at
`2ca7b49`; archived at `archive/sprint-50-executor-overrides-ladder.md`.

### Sprint 51 — review Phases 4 and 5 token economy (implemented on `feat/judge-and-tiered-review`)

Add opt-in LLM-judged criteria evidence, diff payloads for reviewers, cheap
triage review with `escalate`, and the `development_tiered` workflow.

Done: `foreman/engine/judge.py` (heuristic owner + opt-in Anthropic-compatible LLM
judge with head/tail diff truncation), `CompletionEvidence.judged_by`, the
`escalate` outcome, `triage_reviewer`/`frontier_reviewer` roles, the
`{completion_diff}` decision-role prompt payload (`review_diff_max_chars`),
and the `development_tiered` workflow. Merged to `main` at `b53f930`; archived
at `archive/sprint-51-judge-and-tiered-review.md`.

Out of scope (note for later): a tool-enabled "re-review" routing when the
frontier reviewer answers `STEER: need repository context`. Today that carry-
output edge sends the request back to develop; a deeper escape hatch that
re-runs the agentic `code_reviewer` with tools is deferred.

### Sprint 52 — review Phases 6 and 7 supervision and transport cleanup (implemented on `feat/supervision-and-transport`)

Add manager supervision turns for attention-needed events, optimize SSE/watch
polling through SQLite `data_version`, persist retry counts, and complete the
documentation pass for the multi-model/tiered workflow.

Done: `foreman/digest.py`, single `engine.attention_needed` emission per block,
`POST /meta/supervise` (origin=supervision, 409 idempotency, directed
recommend-only), `ForemanStore.data_version()`-gated SSE + watch loops,
persisted `Run.retry_count`, `ProjectSettings` token-economy fields, README +
ADR-0010. This closes the review roadmap. Merged to `main` at `35b667c`;
archived at `archive/sprint-52-supervision-and-transport.md`.

Deferred follow-up: a tool-enabled agentic re-review when the frontier reviewer
answers `STEER: need repository context` (today routes back to develop).

## Tier 3 — Architecture / spec gaps (remaining)

### SSE transport hardening (deferred)

The sprint SSE stream loop polls SQLite directly inside the FastAPI async
generator on a 500 ms interval. This works but is not a final transport design.
Fixing it requires an in-process pub/sub layer (e.g. asyncio queue or
`anyio.Event`) so the generator wakes on a write rather than polling.

- Effort: medium–large
- Urgency: low — current polling is acceptable under normal load
- Prerequisite: decide whether to use an in-process bus or a lightweight broker

## Parking lot

- E2E test coverage for features added in sprints 32–35 (task editing,
  deletion, sprint ordering, date display)
- E2E test coverage for meta agent panel (sprint-40)
- Persist meta agent session history to SQLite (survives server restarts)
- Task `order_index` editing UI within a sprint board (reorder tasks within a
  sprint, similar to sprint ↑/↓ reorder)
- Task priority UI (priority field exists in schema and drawer display but has
  no edit affordance)
- Move task between sprints (no service method or UI; requires task reassignment
  to a different `sprint_id`)
- Codex cost capture — `cost_usd` currently persists as `0.0`; needs Codex
  app-server contract to expose USD pricing
- Run and prompt retention product-level defaults — currently require explicit
  project settings; old runs accumulate if neither is set
