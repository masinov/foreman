# ADR-0001: Runner Session And Backend Contract

- Status: accepted
- Date: 2026-03-30

## Context

Foreman now ships native Claude Code and Codex runners plus monitoring CLI
surfaces that expose persisted runs and events. Future dashboard work needs a
stable contract for:

- what the orchestrator passes into native runners,
- what native runners must persist back into Foreman state,
- when sessions are expected to persist or reset,
- which approval decisions belong to workflows versus runner transports,
- how backend-specific telemetry gaps should appear in durable state.

The current runtime already depends on these choices:

- roles declare `backend`, `session_persistence`, `permission_mode`,
  disallowed tools, timeout, and per-run cost limits,
- the orchestrator persists a `runs` row before every workflow step and stores
  normalized runner events in `events`,
- Claude resumes with a CLI session id, while Codex resumes with a JSON-RPC
  thread id,
- workflow-level human approval pauses are persisted separately from runner
  tool-approval requests,
- monitoring surfaces and future UI work read `session_id`, `cost_usd`,
  `token_count`, and normalized event types directly from SQLite.

Without an accepted ADR here, later runner, monitoring, and dashboard slices
would have to reverse-engineer product behavior from backend-specific code.

## Decision

### 1. Shared runner contract

All native backends must implement the shared `AgentRunner` protocol and accept
`AgentRunConfig` with:

- `backend`
- `model`
- `prompt`
- `working_dir`
- `session_id`
- `permission_mode`
- `disallowed_tools`
- `extra_flags`
- `timeout_seconds`
- `max_cost_usd`

All native backends must normalize backend output into Foreman `AgentEvent`
records and must not crash on unknown backend event shapes. Unexpected items
should be converted into `agent.tool_use` or `agent.message`, while transport
or process failures should surface as `InfrastructureError`.

The orchestrator remains responsible for:

- creating the `runs` row before a workflow step starts,
- persisting normalized events to `events`,
- copying terminal `session_id`, `cost_usd`, `token_count`, and `duration_ms`
  into the `runs` row,
- interpreting completion output into workflow outcomes.

### 2. Session contract

Session persistence is a role-level policy, not a backend-specific special
case.

- Roles with `session_persistence = true` may receive a prior `session_id`.
- Roles with `session_persistence = false` must always start fresh.
- Persistent session scope is `task + role + backend`.
- Runners must return the session identifier they want Foreman to persist when
  the backend exposes one.

The current bootstrap runtime persists `run.session_id` durably for every
native run, but automatic reuse is only guaranteed inside one contiguous
workflow execution path where the orchestrator still holds that value in
memory. Reloading the last persisted same-role session from SQLite on a fresh
orchestrator invocation is not implemented yet and remains explicit follow-up
work.

Human-gate decisions do not own or mutate agent sessions directly. They persist
a human decision run plus `workflow.resumed`, then the resumed agent step
starts or resumes according to the role's session policy.

### 3. Approval and permission boundaries

Foreman separates workflow approvals from runner transport approvals.

- Workflow or domain approvals belong to declarative workflow steps such as
  `_builtin:human_gate` and are persisted as human decisions in runs and
  events.
- Runner-level tool approvals belong to the native backend adapter and must be
  derived from role policy.

Current backend expectations:

- Claude Code receives `permission_mode` and `disallowed_tools` directly from
  the role definition.
- Codex runner auto-responds to JSON-RPC approval requests from the same role
  policy and denies disallowed commands or file mutations at the transport
  layer.
- Domain approvals such as architect-plan approval remain outside the runner
  contract and must not be hidden inside backend-specific approval flows.

### 4. Telemetry and backend contract boundaries

Foreman persists backend telemetry as reported. It does not infer missing cost
data.

- `cost_usd` is authoritative only when the backend reports it.
- `token_count` is persisted independently and may be non-zero even when
  `cost_usd` is `0.0`.
- Monitoring and dashboard surfaces must show token-only runs explicitly
  instead of synthesizing prices.

Current backend-specific consequences:

- Claude is the current source of truth for per-run USD cost.
- Codex currently exposes token usage but not USD pricing through the shipped
  app-server contract, so Codex runs persist accurate token counts with
  `cost_usd = 0.0`.

### 5. Backend adoption rule

Foreman only executes native backends that have an explicit `AgentRunner`
implementation wired into the orchestrator. Unsupported backends must fail
clearly instead of silently falling back to wrapper behavior.

## Consequences

- Dashboard and API work can rely on `runs`, `events`, `session_id`,
  `cost_usd`, and `token_count` as stable runtime surfaces.
- Role definitions remain the source of truth for session persistence and
  runner tool policy.
- Cross-invocation persistent-session reload is now an explicit implementation
  gap rather than an implicit assumption.
- Live activity streaming remains a separate transport and UI boundary
  decision; this ADR does not turn polling `watch` semantics into a streaming
  contract.
- Future changes to session scope, approval handling, or telemetry semantics
  must update or supersede this ADR.
