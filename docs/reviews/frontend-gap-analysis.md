# Frontend gap analysis

Date: 2026-06-13
Scope: `frontend/` (React dashboard) vs. the finished backend (review.md Phases
0–7, plus the supervision-trigger follow-up). Goal: find where the UI fails to
tie into the backend, plus bugs and UX issues.
Method: read `api.js`, `App.jsx`, `components.jsx`, `format.js` and
cross-referenced every call against `dashboard_backend.py` /
`dashboard_service.py` payloads and the new backend features.

> **Update (2026-06-13, branch `feat/frontend-backend-binding`):** Tiers 1 and 2
> of the suggested fixes have landed. Resolved: **A1, A2, A3, A4, C1, B3, B4,
> B5, B6, B7, B1**, plus partial **B2** (complexity + dependency pickers in task
> creation; override/complexity now shown in the drawer). Still open: full **B2**
> override *editor*, **B8** (roles surface), **B9** (meta pagination + origin
> badges), **B10**, and the **D-series** polish. Findings below are kept as
> written; see the per-item “RESOLVED” tags.

## Context

Every file under `frontend/src/` is dated **jun 12** — before any review-roadmap
backend work (jun 13). The frontend predates the multi-model fleet, executor
overrides, the LLM judge, tiered review, manager persistence, and supervision.
As a result it is **functionally intact for the pre-roadmap surface** (projects,
sprints, tasks, board, activity stream, human gates, the meta-agent chat) but
**blind to almost everything the roadmap added.**

What still works correctly (verified):

- The SSE live stream — the backend sends `{type:"event", event:{…}}`
  (`dashboard_service.py:526`) and the client expects exactly that
  (`App.jsx:279`). Live updates are fine.
- The meta-agent chat NDJSON contract (`text_delta`/`tool_use`/`done`/`error`)
  still matches after the Phase 2 rewrite (`meta_agent.py` vs
  `components.jsx:1739`). Chat works.
- CRUD, board, gates, approve/deny, stop/cancel/delete, settings round-trip,
  pagination of sprint events.

---

## A. Bugs (functional)

### A1 — New-task "Context" field is silently dropped
`NewTaskModal` collects a **Context (optional)** field and submits it as
`context` (`components.jsx:1574`), but `App.handleCreateTask` destructures only
`{title, taskType, acceptanceCriteria}` (`App.jsx:465`) and `services.createTask`
sends only those three (`api.js:106`). The user's context/description text
vanishes on every dashboard-created task. (The backend `create_task` wouldn't
accept it anyway — see C1.)

### A2 — Run/Stop toggle reads the wrong field
Phase 0.6 added an authoritative `agent_running` boolean (real subprocess
registry) to `get_project`/`list_projects` **specifically so the UI stops
inferring Run/Stop from task status**. The frontend never consumed it: both the
sprint header (`App.jsx:799`) and the project queue (`components.jsx` SprintList
`project.status === "running"`) still gate on `get_project_status`, which simply
returns `"running"` when any task is `in_progress` (`dashboard_service.py`). So
after a crash, an external `foreman run`, or a finished-but-not-cleared task, the
toggle misreports whether an agent is actually running. The backend half of the
fix shipped; the frontend half did not.

### A3 — Settings panel writes dead keys
`SettingsPanel` renders toggles/inputs for keys that **`ProjectSettings` never
reads**: `approve_merges`, `approve_task_completion`,
`approve_sprint_completion`, `agent_can_create_tasks`, `approve_architect_plans`,
`max_tokens_per_task`, `max_infra_retries` (`components.jsx:1235‑1351`).
`update_project_settings` merges raw settings into the JSON blob without
validating against `ProjectSettings.from_raw` (`dashboard_service.py:197`), so
these persist but are inert. The operator believes they are configuring
behavior that the engine ignores.

### A4 — Selecting the Codex meta backend breaks the manager
The Meta Agent settings expose a backend `<select>` with a **Codex** option
(`components.jsx:1282`) written to `meta_agent_backend`. `meta_agent.py` only
supports `claude` and returns an error turn for anything else. Choosing Codex
silently bricks every manager turn.

---

## B. Backend↔frontend binding gaps (roadmap features with no UI)

### B1 — Supervision (Phase 6) is entirely unwired *(highest-value gap)*
There is no `superviseMeta` method in `api.js`, no handling of
`engine.attention_needed` events, and no "ask the manager" affordance. The
`POST /api/projects/{id}/meta/supervise` endpoint, the attention digest, and the
whole engine→manager supervision thread are invisible. The dashboard is the
intended trigger surface ("the dashboard can poll/SSE these events and call the
endpoint") and currently does none of it.

### B2 — Per-task executor overrides + complexity (Phase 3) invisible
No UI to view or set `executor_overrides` or `complexity`. `TaskDetailDrawer`
omits both (it has the data — `get_task` returns them). `NewTaskModal` has no
complexity. The manager's core differentiated-dispatch lever is unreachable from
the UI. (`updateTask` is a generic PATCH and the backend already accepts
`executor_overrides`, so this is UI-only work.)

### B3 — Completion evidence / proof gate (Phases 0.7 & 4) invisible
`TaskDetailDrawer` shows description, details, deps, criteria, blocked reason,
and run history — but **nothing** from `completion_evidence` (verdict,
`proof_status`, score, criteria checklist, `judged_by`), even though `get_task`
returns it. The single most important "is this actually done, and who judged it"
signal is hidden from the operator.

### B4 — Model transparency (Phase 3) missing
Run history rows show role, step, duration, status, tokens — but not the run's
`model` (`components.jsx:1105`). `workflow.model_selected` ladder escalations
have no friendly rendering. You cannot see which model handled a step or that an
escalation happened.

### B5 — Token-economy settings not exposed
`meta_agent_model` (the frontier manager model — a headline Phase 2 control),
`judge_base_url` / `judge_model` / `judge_api_key_env` / `judge_max_diff_chars`
(Phase 4), `review_diff_max_chars` (Phase 5), and `default_model` (the fleet
default) are all absent from `SettingsPanel`.

### B6 — Real resource gates not exposed
The "Resource Limits" section shows the **non-existent** `max_tokens_per_task`
and omits the gates the engine actually enforces: `cost_limit_per_task_usd`,
`cost_limit_per_sprint_usd`, `time_limit_per_task_ms`,
`completion_guard_enabled`, `event_retention_days`, `test_command`.

### B7 — Tiered workflow unselectable
`WORKFLOW_OPTIONS` (`components.jsx:1148`) lists `development`,
`development_with_architect`, `development_secure` — **`development_tiered` is
missing**, so the Phase 5 workflow cannot be chosen from New Project or Settings.
The `escalate` outcome and triage/frontier roles also have no special display.

### B8 — Roles API unused
`GET /api/roles` and `PATCH /api/roles/{id}` exist but `api.js` has no
`listRoles`/`updateRole` and there is no role inspection/editing surface.

### B9 — Meta history: no pagination, no provenance
`MetaAgentPanel` loads `metaHistory(projectId)` once with no `limit`/`before`
cursor and ignores `has_more` (`components.jsx:1709`), so long manager threads
truncate with no "load older". It also doesn't distinguish turn `origin` —
`supervision` turns render identically to `chat`, so the operator can't see when
the engine (vs. they) drove a turn.

### B10 — `zero_cost_token_runs` not surfaced
It's in the `totals` payloads (Phase 1.4) but the UI never shows the
"tokens (cost unknown for N runs)" caveat for third-party endpoints.

---

## C. Backend API divergence the frontend exposes

### C1 — Dashboard `create_task` lags the CLI
`POST /api/sprints/{id}/tasks` → `create_task` accepts only
`title`/`task_type`/`acceptance_criteria` (`dashboard_service.py`), while the CLI
`foreman task add` gained `--description`, `--sprint`, `--depends-on`,
`--complexity`. Even `create_sprint`'s `initial_tasks` path accepts
`description` (`dashboard_service.py:414`) — so the standalone endpoint is behind
its own sibling. **This is a backend gap**, not only a UI one: closing B2 needs
`create_task` to accept `description`, `depends_on`, and `complexity` first.

---

## D. Smaller UX issues

- **D1** Dependencies are display-only; no add/remove in the drawer or
  create modal (`components.jsx:1010`).
- **D2** The board card's Deny button reuses the shared `denyNote` state (likely
  empty) with no inline note field; only the drawer has the note textarea.
- **D3** Dashboard "New Project" creates a bare `Project` row — no `spec_path`,
  no repo validation, no `.foreman` scaffold — diverging from `foreman init`.
- **D4** `MetaAgentPanel` renders only in the project view (inside `SprintList`),
  not in the sprint board view, so the manager disappears once you drill into a
  sprint.
- **D5** The committed `foreman/dashboard_frontend_dist/` (what `foreman
  dashboard` serves) and the source both predate the roadmap; any fixes here
  require `npm --prefix frontend run build` to reach the served surface.

---

## Suggested priority

**Tier 1 — correctness / honesty (small, high value)**
- A1 (drop-context bug), A3/A4 (dead + dangerous settings), A2 (`agent_running`).
- C1 (extend `create_task`) — unblocks B2.

**Tier 2 — make the roadmap visible**
- B3 (completion evidence in the drawer) and B4 (run model) — highest
  signal-to-effort; the proof gate is the product's spine.
- B1 (supervision: `superviseMeta` + an attention banner/button driven off
  `engine.attention_needed`).
- B5/B6/B7 (settings rewrite against the real `ProjectSettings` schema + add
  `development_tiered`).

**Tier 3 — depth**
- B2 (override/complexity editor), B8 (roles surface), B9 (meta pagination +
  origin badges), B10, and the D-series polish.

A clean first slice would pair the settings rewrite (A3/A4/B5/B6/B7 — all in
`SettingsPanel`) with the `create_task` extension (C1 + A1), since those are the
"the UI is lying or losing data" problems. Evidence visibility (B3/B4) is the
best follow-up.

---

## Validation notes

- Frontend tests: `npm --prefix frontend test` (vitest). Any change to served
  output also needs `npm --prefix frontend run build` to refresh
  `foreman/dashboard_frontend_dist/`.
- No backend code was changed by this analysis.
