# Foreman Backend Completion Spec

Status: ready for implementation
Audience: implementing agent. Read `AGENTS.md`, `docs/STATUS.md`, and the relevant source files before each phase.
Scope: backend only (`foreman/` package, `roles/`, `workflows/`, migrations, CLI). Frontend changes are noted only where an API contract changes; do not redesign the UI.

## Objective

Turn Foreman into a complete multi-model orchestration system in which a frontier "manager" model (via the meta-agent chat panel) plans work interactively with the human, promotes plans into persisted tasks, and assigns them to cheaper worker models, while the engine routes review/escalation so that frontier tokens are only spent on planning, adjudication, and hard cases.

Strategy decisions already made (do not revisit):

- **Reuse existing harnesses.** Cheap models (Minimax M3, DeepSeek, GLM, Kimi, OpenRouter-via-proxy) run through the existing `ClaudeCodeRunner` against Anthropic-compatible endpoints, selected per role via environment injection. **Do not build a custom OpenAI-protocol runner.**
- **No parallel/multi-worktree execution in this spec.** Sequential task execution is acceptable. Do not add worker pools.
- **No dollar-cost budget system in this spec.** Token counts must be recorded correctly; USD precision is out of scope. Existing cost gates stay as-is.
- **The meta-agent chat panel stays** and becomes the primary human↔manager interface. It is hardened, not replaced.

Each phase below is independently mergeable and ends with explicit acceptance criteria. Implement phases in order. Within a phase, items are ordered by dependency.

---

## Phase 0 — Correctness fixes

These are real bugs found in the current code. Fix all of them first; several later phases build on the corrected behavior. Each fix needs a regression test.

### 0.1 `UnboundLocalError` on the first native role step (critical)

`foreman/orchestrator.py`, `run_workflow_from_step`, native-role branch:

```python
current_task.assigned_role = role.id
self.store.save_task(current_task)

self._emit_event(
    run,                      # <-- `run` is not yet bound on the first iteration
    "engine.role_policy",
    ...
)
```

`run` is created later by `self._create_running_run(...)`. On the first workflow step (e.g. `develop` in the `development` workflow) this raises `UnboundLocalError`; on later iterations it silently attaches the `engine.role_policy` event to the *previous* step's run.

**Fix:** move the `engine.role_policy` emission to immediately after `run = self._create_running_run(...)` (before `agent.prompt`).

**Test:** run a task through a stub `agent_executor` with the real workflow loop; assert the first step completes and that `engine.role_policy` is attached to the run whose `workflow_step` matches the step.

### 0.2 `NameError` when an agent emits `signal.task_created` (critical)

`foreman/orchestrator.py`, `_apply_agent_signal`, in the `signal.task_created` branch:

```python
self._emit_event(
    run,                      # <-- `run` is not a parameter of this method
    "engine.task_created",
    ...
)
```

**Fix:** change the signature to `_apply_agent_signal(self, run: Run, task, project, role_id, event_record)` and update both call sites (`_emit_agent_events` and `_persist_agent_event`).

**Test:** feed a fake `signal.task_created` agent event through `_persist_agent_event`; assert a new task row exists and an `engine.task_created` event is persisted against the active run.

### 0.3 Missing `uuid4` import in the CLI (critical)

`foreman/cli.py`, `handle_waive_merge` uses `uuid4()` but the module never imports it → `NameError` on every `foreman waive-merge` invocation.

**Fix:** `from uuid import uuid4` at module top.

**Test:** CLI subprocess test exercising `foreman waive-merge` end-to-end against a temp DB.

### 0.4 Merge conflicts never take the `completion:conflict` transition (high)

`foreman/builtins.py`, `_merge`: the conflict branch returns `BuiltinResult(outcome="failure", ...)`. The workflows define a dedicated `completion:conflict` transition (which also resets `step_visit_counts` in the orchestrator), but it can never fire because:

1. `_merge` reports `failure`, not `conflict`, so the generic `completion:failure` edge wins; and
2. even if it returned `"conflict"`, `normalize_agent_outcome` maps unknown strings to `ERROR`.

Consequences today: conflict recovery only works via the fragile text sniff in `_is_merge_conflict_feedback`, and conflict loops burn the step-visit budget that `workflow.step_visit_reset` was designed to refund.

**Fix:**
1. In `foreman/outcomes.py` add `CONFLICT = "conflict"`, include it in `CANONICAL_OUTCOMES`, and make `normalize_agent_outcome` pass `"conflict"` through.
2. In `_merge`, the conflict branch returns `outcome=CONFLICT` (keep the detailed guidance text in `detail`).
3. Keep `_is_merge_conflict_feedback` as a fallback, but the primary path is now the explicit outcome.

**Test:** orchestrator test where a fake merge produces a conflict; assert the `completion:conflict` transition fires, `step_visit_counts` resets, and the develop step receives the carried guidance.

### 0.5 Foreign-key violation when persisting human events on run-less tasks (high)

`events.run_id` has `REFERENCES runs(id)` and the store opens connections with `PRAGMA foreign_keys = ON`. Two `DashboardService` methods insert events with `run_id="none"` when the task has no runs yet:

- `create_human_message`
- `stop_agent` (per-task loop)

Both will raise `sqlite3.IntegrityError` for fresh tasks. (`stop_task` and `update_task_fields` already solved this with synthetic runs — that is the correct pattern.)

**Fix:** extract a private helper on `DashboardService`:

```python
def _ensure_event_run(self, task: Task, *, step: str, outcome: str) -> str:
    """Return the latest run id for the task, creating a synthetic
    dashboard run when no run exists (FK safety)."""
```

Use it in `create_human_message`, `stop_agent`, `stop_task`, and `update_task_fields` (replacing the duplicated inline logic in the latter two).

**Additional fix while there:** `create_human_message` currently attaches the event to `runs[0]` — the *oldest* run (`list_runs` orders ascending). Use the latest run instead.

**Test:** post a human message to a task with zero runs via the FastAPI transport; assert 200, a synthetic run exists, and the event references it.

### 0.6 Dashboard agent process registry never works across requests (high)

`foreman/dashboard_backend.py` constructs a fresh `DashboardService` per request (`with_api` → `_open_store` → `DashboardService(store)`), but the subprocess registry lives on the instance (`self._running_procs`). Therefore:

- `start_agent`'s double-start guard never trips (the dict is always empty),
- nothing ever terminates the spawned `foreman run` subprocess — `stop_agent` only flips task rows to blocked while the orchestrator process keeps running, fighting the user's intent (this is the "confirm/fix dashboard Run subprocess wiring" backlog item).

**Fix:**
1. Move the registry to module level in `dashboard_service.py`:
   ```python
   _RUNNING_PROCS: dict[str, subprocess.Popen[bytes]] = {}
   _RUNNING_PROCS_LOCK = threading.Lock()
   ```
   All reads/writes go through the lock. `start_agent` consults and populates it; the cleanup thread removes entries on exit.
2. `stop_agent` first terminates the registered subprocess if alive (`proc.terminate()`, wait up to ~5 s, then `proc.kill()`), emits one `human.stop_requested` project-scoped event, **then** performs the existing per-task blocking so the persisted state reflects the stop.
3. Add `"agent_running": bool` to the `list_projects` and `get_project` payloads (derived from the registry) so the UI's Run/Stop toggle reflects reality instead of inferring from task statuses.

**Test:** service-level test with a fake `Popen` (long-lived dummy process): start → second start raises `DashboardValidationError`; stop → process terminated and registry empty.

### 0.7 Completion evidence is rebuilt on every prompt for every role (medium, performance)

`foreman/orchestrator.py`, `_build_prompt`:

```python
if evidence is None and role.id in self.roles:   # always true for any loaded role
    evidence = self.build_completion_evidence(task, project)
```

The guard is vacuous, so every developer prompt triggers a full evidence build (multiple git subprocesses, event scans). The comment says it should happen "at first reviewer render".

**Fix:** build evidence only when the role actually consumes it: `if evidence is None and role.completion.output.extract_decision:`. Additionally, evidence cached on the task must be **invalidated when the branch head moves**: before reuse, compare `evidence.head_sha` against the current branch head; rebuild on mismatch (otherwise a reviewer on a second review cycle sees stale evidence from the first cycle).

**Test:** assert a developer-step prompt build performs no evidence construction (spy on `build_completion_evidence`); assert reviewer prompt rebuilds evidence after a new commit on the task branch.

### 0.8 `cancel_task` (dashboard) leaves stale workflow state (low)

`DashboardService.cancel_task` only sets `status="cancelled"`. The CLI's `handle_task_cancel` also clears `blocked_reason`, `workflow_current_step`, `workflow_carried_output` and sets `completed_at`. A cancelled task with a persisted `workflow_current_step` can confuse resume logic and the UI.

**Fix:** mirror the CLI behavior in the service method.

### 0.9 Remove the dead `foreman/executor.py` path (low, hygiene)

`ClaudeCodeExecutor` duplicates the native-runner execution path inside the orchestrator and has already drifted (no signal handling, no retry normalization, separate config). Nothing in the shipped product constructs it.

**Fix:** delete `foreman/executor.py` and `tests/test_executor.py`; keep the `AgentExecutor` protocol in `orchestrator.py` (it is the test seam). Update CHANGELOG. If any script imports it, fix the script.

### Phase 0 acceptance

- All new regression tests pass; full suite green (`./venv/bin/python -m unittest discover -s tests -v`).
- A manual end-to-end run of the `development` workflow with the real Claude Code backend completes develop → review → test → merge → done with no `UnboundLocalError`/`NameError`/FK errors in events.

---

## Phase 1 — Multi-model fleet via per-role environment injection

Goal: any role can target any Anthropic-compatible endpoint (Minimax, DeepSeek, GLM, Kimi, or an OpenRouter/LiteLLM proxy) using the **unchanged** Claude Code harness.

### 1.1 Role schema: `[agent.env]`

`roles/*.toml` gains an optional table:

```toml
[agent]
backend = "claude_code"
model = "MiniMax-M2"
session_persistence = true
permission_mode = "bypassPermissions"

[agent.env]
ANTHROPIC_BASE_URL = "https://api.minimax.io/anthropic"
ANTHROPIC_AUTH_TOKEN = "env:MINIMAX_API_KEY"
CLAUDE_CONFIG_DIR = "env:FOREMAN_MINIMAX_CONFIG_DIR?~/.foreman/claude-minimax"
```

Value resolution convention (resolve at run-config build time, **never** persist resolved secrets):

- `"literal string"` → used as-is.
- `"env:NAME"` → value of host environment variable `NAME`; if unset, raise a `PreflightError`-style failure *before* `agent.started` (consistent with existing preflight semantics — one explicit failed run, no retries).
- `"env:NAME?fallback"` → host env var with a literal fallback.
- Values are additionally passed through `os.path.expanduser` when the key ends in `_DIR` or `_PATH`.

Changes:

- `foreman/roles.py`: `AgentConfig` gains `env: dict[str, str] = field(default_factory=dict)`; `load_role` reads `_as_mapping(agent_data.get("env"), default={})` and validates all values are strings.
- New helper `foreman/runner/env.py` with `resolve_env(spec: Mapping[str, str]) -> dict[str, str]` implementing the convention above, raising `PreflightError` on missing required vars. Unit-test it directly.

### 1.2 Runner plumbing

- `foreman/runner/base.py`: `AgentRunConfig` gains `env: dict[str, str] = field(default_factory=dict)`.
- `ClaudeCodeRunner.run` and `CodexRunner` (`_JsonRpcClient.__init__`): pass `env={**os.environ, **config.env}` to `Popen` **only when `config.env` is non-empty**; otherwise pass nothing (preserves current behavior and existing test fakes that don't accept `env`).
- `foreman/orchestrator.py`, `_execute_native_runner_step` (and the retry config build): populate `config.env = resolve_env(role.agent.env)`. Resolution failures must surface as the existing preflight-failure path (one failed run, `agent.error` with `preflight_failed: true`).

### 1.3 Session isolation per endpoint

Document (in `AGENTS.md`/README, and enforce nothing): roles pointing at different endpoints **should** set distinct `CLAUDE_CONFIG_DIR` values so `--resume` session pools don't mix providers. Add this to the example role file.

### 1.4 Token accounting honesty for third-party endpoints

Third-party endpoints behind Claude Code typically report `total_cost_usd` as `0` while token counts are accurate. The store already tracks `zero_cost_token_runs` and `handle_cost` prints a note. Two small changes:

- `dashboard_service.run_totals` passthroughs already include `zero_cost_token_runs` — expose it in the `get_project` and `get_sprint` payloads so the UI can show "tokens (cost unknown for N runs)".
- Nothing else. Do **not** build a price table in this phase.

### 1.5 Shipped example role

Add `roles/developer_worker.toml`: a copy of `developer.toml` with id `developer_worker`, name "Developer (worker fleet)", a placeholder `[agent.env]` block (Minimax example, commented), and `model = ""` so the project `default_model` applies. This is the role the manager will assign cheap work to in later phases. Update `foreman roles` output expectations in tests.

### Phase 1 acceptance

- `resolve_env` unit tests cover literal, `env:`, `env:?fallback`, missing-required (raises), `_DIR` expansion.
- Runner test: fake `popen_factory` asserts it receives the merged environment when `[agent.env]` is set and the default environment when not.
- Orchestrator test: missing required env var produces exactly one failed run with `preflight_failed: true` and consumes no infra retries.
- Manual smoke (documented in README): point `developer_worker` at any Anthropic-compatible endpoint and complete one task end-to-end.

---

## Phase 2 — Manager hardening (meta-agent)

Goal: the chat panel becomes a durable planning partner. Three sub-goals: (a) persistence, (b) always-fresh world state, (c) an explicit promotion/assignment contract.

### 2.1 Persist sessions and turns (migration 11)

Add to `foreman/migrations.py`:

```sql
-- migration 11: meta-agent session persistence
CREATE TABLE IF NOT EXISTS meta_sessions (
    project_id   TEXT PRIMARY KEY REFERENCES projects(id),
    session_id   TEXT,              -- Claude Code --resume id, nullable
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta_turns (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id),
    role         TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    text         TEXT NOT NULL,
    tool_uses_json TEXT NOT NULL DEFAULT '[]',
    origin       TEXT NOT NULL DEFAULT 'chat',   -- 'chat' | 'supervision' (Phase 6)
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_meta_turns_project
ON meta_turns(project_id, created_at);
```

Store methods in `foreman/store.py`: `get_meta_session(project_id)`, `save_meta_session(project_id, session_id)`, `append_meta_turn(...)`, `list_meta_turns(project_id, limit, before_id=None)`, `clear_meta_session(project_id)` (deletes the session row and turns).

### 2.2 Rework `foreman/meta_agent.py` to be store-backed

- `process_message(project_id, message, *, store, project, sprints, executable)` — takes the store (the dashboard endpoints already hold one; pass `db_path` and open per-call if lifetime is awkward, mirroring `_open_store`).
- Drop the in-memory `_sessions` registry entirely. Session id comes from `meta_sessions`; history from `meta_turns`.
- Persist the user turn before invoking Claude Code; persist the assistant turn **incrementally-safe**: write it in the `finally` path with whatever text accumulated, flagged with an `"interrupted": true` entry in `tool_uses_json` if the stream errored, so a crash never silently drops a turn.
- `get_history` / `clear_session` become thin store wrappers. `GET /api/projects/{id}/meta/history` should now support `limit` (default 50) and `before` cursor query params, returning `has_more` (same pattern as sprint events).
- Pass `--model` to the meta-agent subprocess from a new project setting `meta_agent_model` (default empty → harness default). The manager seat is where you want the frontier model; make it configurable.

### 2.3 Fresh state header on every turn

Replace the "context only on first message" behavior:

- New function `build_state_header(store, project) -> str` producing a **compact** (~target ≤ 1,500 tokens) snapshot: project name/workflow/autonomy; sprint list with status + task counts; for the active sprint, a task table (`id | status | type | title | assigned model override | blocked_reason (truncated 80 chars)`); pending decision gates; last 5 noteworthy events (blocked / evidence-failed / sprint lifecycle). Plain text, fixed format.
- Every turn's prompt is: `state header + "---" + (first turn only: the operating contract from 2.4) + user message`.
- The header must state explicitly: "This state block is regenerated each turn and reflects the database now; trust it over your memory of earlier turns."

### 2.4 The promotion/assignment contract

Rewrite `_build_context` into an explicit operating contract injected on the first turn of a session (and re-injected after `clear_session`). It must enumerate, with exact command syntax, everything the manager may do via the `foreman` CLI:

- inspect: `foreman board`, `foreman task show`, `foreman history`, `foreman cost`, `foreman sprint list`
- plan: `foreman sprint add <project> --title ... --goal ...`
- promote: `foreman task add <project> --title ... --type ... --criteria ... --description ... --sprint <sprint-id> --depends-on <task-id,...>`
- assign (Phase 3): `foreman task override <task-id> --step develop --model ... [--ladder-start N]`
- steer: `foreman approve / deny --note`, `foreman task block/unblock/cancel`
- and the hard rules: never edit `.foreman/`, never merge manually, never run `foreman run` itself (the human or supervision loop triggers runs), always re-read the state header before acting.

**CLI gaps to close so the contract is honest** (`foreman/cli.py`):

- `foreman task add` gains `--description` and `--sprint SPRINT_ID` (explicit target instead of "active else first planned") and `--depends-on` (comma-separated task ids, validated to exist in the same project, stored in `depends_on_task_ids`).
- `foreman sprint add` is fine as-is.

### Phase 2 acceptance

- Migration 11 applies cleanly on fresh and existing DBs (`tests/test_migrations.py` pattern).
- Dashboard restart preserves chat history and session resumption (integration test through the FastAPI endpoints with a faked Claude subprocess).
- A scripted meta turn whose fake model output shells `foreman task add ... --sprint ... --depends-on ...` results in a correctly linked task.
- State header builder has a unit test pinning the format and the truncation rules.

---

## Phase 3 — Per-task executor overrides + escalation ladder

Goal: the manager can differentiate dispatch per task; the engine escalates model tier automatically on repeated failure.

### 3.1 Schema (migration 12)

```sql
-- migration 12: per-task executor overrides and architect complexity
ALTER TABLE tasks ADD COLUMN executor_overrides_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE tasks ADD COLUMN complexity TEXT;
```

`Task` model gains `executor_overrides: dict[str, Any]` and `complexity: str | None`. Store row mapping + `save_task` updated. Override shape (validate on write):

```json
{
  "models":        {"develop": "MiniMax-M2", "review": "claude-opus-4-8"},
  "ladder_start":  0
}
```

Keys of `"models"` are **workflow step ids**. Unknown keys in the top-level object are rejected.

### 3.2 Role schema: `model_ladder`

`[agent]` gains optional `model_ladder = ["model-a", "model-b", ...]` (list of strings, may be empty/absent). `AgentConfig.model_ladder: tuple[str, ...]`. When present, it supersedes `model` for tier selection; `model` remains the single-model fallback.

### 3.3 Model resolution

New pure function in `foreman/orchestrator.py` (unit-test it directly):

```python
def resolve_step_model(
    *, task: Task, role: RoleDefinition, project: Project,
    step_id: str, visit_count: int,
) -> str | None:
```

Precedence:

1. `task.executor_overrides["models"][step_id]` if set → use it for visit 1; **ladder still applies above it** for later visits if the override model appears in the role ladder (resume escalation from its index + (visit-1)); if it doesn't appear in the ladder, keep the override for all visits (the manager pinned it deliberately).
2. else if `role.agent.model_ladder`: index = `min(ladder_start + visit_count - 1, len(ladder) - 1)` where `ladder_start = task.executor_overrides.get("ladder_start")`, falling back to a complexity map: `{"small": 0, "medium": 0, "large": 1}` when `task.complexity` is set, else 0.
3. else `role.agent.model` if non-empty.
4. else project setting `default_model`.
5. else `None` (harness default).

Wire it into the native-runner path (`_execute_native_runner_step`) and the prompt/run-record `model` field in `run_workflow_from_step`. Emit a `workflow.model_selected` event per agent step: `{step, model, visit_count, source: "override|ladder|role|project_default"}` — the manager and dashboard read this to see escalations happen.

**Interaction with env injection:** if different ladder rungs need different endpoints, that is expressed by using different *roles* per workflow step, not by per-model env switching. Document this limitation explicitly in the role docs; do not implement per-model env maps.

### 3.4 Persist architect complexity

`workflows/development_with_architect.toml` flow: the architect emits task JSON including `"complexity"`, but nothing consumes it. Wherever architect output is turned into tasks (today that is manual / manager-driven; also `signal.task_created`):

- `signals.py`: `task_created` payload accepts optional `"complexity"` in `{"small","medium","large"}` (validated); `_apply_agent_signal` writes it to the new column.
- `foreman task add` gains `--complexity {small,medium,large}`.

### 3.5 CLI: `foreman task override`

```
foreman task override TASK_ID [--step STEP --model MODEL]... [--ladder-start N] [--clear]
```

Reads, validates (step ids checked against the project's workflow), merges, and saves `executor_overrides_json`. Prints the resulting object. `--clear` resets to `{}`. Also expose it on the API: extend `PATCH /api/tasks/{task_id}` allowed fields with `executor_overrides` (full-object replace, validated), and include `executor_overrides` and `complexity` in `get_task` / `list_sprint_tasks` payloads.

### Phase 3 acceptance

- `resolve_step_model` unit tests cover all five precedence branches plus the override-in-ladder resume case.
- Orchestrator integration test: a task with `max_step_visits=3` and ladder `[A, B, C]` whose fake agent fails twice runs A, then B, then C, and `workflow.model_selected` events record the progression.
- `foreman task override` round-trips through the CLI and is visible in `foreman task show`.

---

## Phase 4 — Evidence quality: LLM-judged criteria checklist

Goal: replace the keyword-overlap heuristic in `_criterion_addressed` with a cheap-model judgment, so `proof_status` is trustworthy enough for the manager and frontier reviewer to lean on. The judge is a **direct HTTP call**, not a harness session — it needs no tools and must be cheap and fast.

### 4.1 `foreman/judge.py`

```python
@dataclass(frozen=True)
class CriteriaJudgment:
    checklist: tuple[dict[str, str], ...]   # {criterion, status, evidence}
    judged_by: str                          # model id, or "heuristic"

def judge_criteria(
    *, criteria: list[str], diff_text: str, agent_summary: str,
    settings: Mapping[str, Any], timeout_seconds: float = 60.0,
) -> CriteriaJudgment:
```

- Project settings (all optional): `judge_base_url`, `judge_model`, `judge_api_key_env`, `judge_max_diff_chars` (default 24000). If `judge_base_url`/`judge_model` are unset, return the **existing heuristic** result with `judged_by="heuristic"` — the feature is strictly opt-in and the heuristic stays as the zero-config fallback.
- Use `httpx` (already a dependency). Speak the Anthropic Messages API shape (`/v1/messages`) since the fleet endpoints are Anthropic-compatible; system prompt demands a JSON array `[{"criterion": "...", "status": "passed|partial|failed", "evidence": "<one line>"}]` and nothing else; parse with a fence-stripping fallback.
- Diff text is truncated to `judge_max_diff_chars` with head+tail split (keep first 70% / last 30%) and an explicit `[...truncated N chars...]` marker.
- On any error (HTTP, timeout, unparseable output): log a warning event-style string in the return path and fall back to the heuristic. **Evidence building must never crash the workflow** (matches the existing defensive posture in `_build_completion_evidence`).

### 4.2 Wire into `build_completion_evidence`

In `foreman/orchestrator.py`:

- Move the current keyword logic into `judge.py` as the heuristic fallback (`_criterion_addressed` and its caller loop) so there is one owner.
- `build_completion_evidence` collects `criteria_list`, the capped diff (reuse `_safe_branch_diff` but with `git diff` content, not just `--stat` — add a `_safe_branch_diff_content` helper), and the latest developer `outcome_detail`, then calls `judge_criteria`.
- Map the checklist into the existing fields (`criteria_addressed` = count passed, `criteria_partially_addressed` = count partial, `criteria_checklist`, and the downstream `proof_status` derivation unchanged).
- Record `judged_by` in a new `CompletionEvidence.judged_by: str = "heuristic"` field (dataclass default keeps old serialized evidence loadable) and include it in the `engine.completion_evidence` event payload.

### Phase 4 acceptance

- `judge.py` unit tests with a fake httpx transport: happy path, fenced JSON, malformed output → heuristic fallback, timeout → fallback, unset settings → heuristic.
- Evidence built with judge configured shows `judged_by=<model>` in the `engine.completion_evidence` event; with it unset, behavior is byte-identical to today (regression test against current heuristic outputs).

---

## Phase 5 — Tiered review: triage step + diff-payload frontier review

Goal: the frontier model only reviews work that a cheap reviewer couldn't confidently adjudicate, and when it does review, it reads a curated payload instead of exploring the repo.

### 5.1 New outcome: `escalate`

- `foreman/outcomes.py`: add `ESCALATE = "escalate"`, include in `CANONICAL_OUTCOMES`.
- `_extract_decision_output` in `orchestrator.py`: recognize `ESCALATE` / `ESCALATE: <reason>` lines exactly like the other decisions (reason carried as detail).
- `foreman/workflows.py` `_VALID_OUTCOMES`: add `"triage_reviewer": {"approve", "deny", "escalate"}`.

### 5.2 New role: `roles/triage_reviewer.toml`

Cheap-model decision role (`extract_decision = true`, all mutating tools + Bash disallowed, short timeout). Prompt receives the same evidence block plus the new diff payload (5.3) and must return exactly one of `APPROVE`, `DENY: <reason>`, `ESCALATE: <why this needs the senior reviewer>`. The prompt instructs: escalate when evidence verdict is weak/insufficient, when the diff touches security-sensitive or architectural files, or when it is unsure — **never** approve to avoid escalating.

### 5.3 Diff payload template variable

`_build_prompt` gains `completion_diff`: capped unified diff of `default_branch...branch_name` (new `review_diff_max_chars` project setting, default 16000, same head/tail truncation as 4.1), populated **only** for roles with `extract_decision = true` (other roles get `""`). Add `{completion_diff}` sections to `code_reviewer.toml`, `security_reviewer.toml`, and the new triage role.

### 5.4 New role: `roles/frontier_reviewer.toml` + workflow

- `frontier_reviewer`: decision role, **all tools disallowed** (pure read-the-payload review), prompt = task + criteria + evidence + criteria checklist + `{completion_diff}` + developer summary. Returns `APPROVE` / `DENY:` / `STEER:`. Add `"frontier_reviewer": {"approve", "deny", "steer"}` to `_VALID_OUTCOMES`.
- New `workflows/development_tiered.toml`:

```
develop → triage
triage  --approve-->  test
triage  --deny----->  develop (carry_output)
triage  --escalate->  review          # frontier_reviewer
review  --approve-->  test
review  --deny/steer-> develop (carry_output)
test/merge/done edges identical to development.toml (including completion:conflict)
```

- Validate via the existing loader tests; add the workflow to the `foreman workflows` expectations.

### 5.5 Keep the agentic reviewer as the escape hatch

Do not delete or de-tool `code_reviewer`. If the frontier reviewer answers `STEER: need repository context`, the carry-output edge sends that back to develop today; a deeper "tool-enabled re-review" routing is **out of scope** — note it in the backlog doc instead.

### Phase 5 acceptance

- Workflow loader accepts `development_tiered`; `validate()` catches a deliberately broken copy (test).
- Orchestrator test with fakes: triage `ESCALATE:` routes to the review step with the reason visible in events; triage `APPROVE` skips frontier entirely.
- Prompt-construction test: developer prompt contains no diff payload; reviewer prompts contain the capped diff with the truncation marker when oversized.

---

## Phase 6 — Supervision turns (engine → manager)

Goal: the same persisted meta session receives compact, event-triggered turns when the engine needs a decision, so the human sees a continuous thread: planning in the morning, autonomous supervision during the day.

### 6.1 Digest builder

`foreman/digest.py`: `build_attention_digest(store, project, *, trigger: str, task_id: str | None) -> str`. Compact text (~≤800 tokens): the trigger (`task_blocked`, `evidence_failed`, `loop_limit`, `sprint_resolved`), the affected task's row (status, step, visits, blocked reason, evidence verdict + failure reasons, last run outcome detail truncated to 400 chars), and the manager's allowed responses (the contract verbs from 2.4). Unit-test the format.

### 6.2 Trigger plumbing

Cheapest robust mechanism — no daemon, no new transport:

- Orchestrator: whenever a task transitions to `blocked` inside `run_workflow_from_step` / `_apply_agent_signal`, or `proof_status` lands `failed` at a guard, emit the existing events **plus** one `engine.attention_needed` event with `{trigger, task_id}` payload.
- New endpoint `POST /api/projects/{project_id}/meta/supervise`: body `{event_id}` (an `engine.attention_needed` event). It builds the digest, runs one meta turn through `process_message` with `origin="supervision"` (turn rows flagged accordingly), and streams the NDJSON response exactly like `meta/message`. Idempotency: store the consumed `event_id` in the turn's `tool_uses_json` metadata and reject duplicates with 409.
- The dashboard frontend can poll/SSE these events and call the endpoint (or the human clicks a "ask the manager" button). **Auto-invocation policy is a frontend/ops concern; the backend only provides the endpoint.** Gate the manager's permission to *act* (vs. merely recommend) on `project.autonomy_level`: in `directed` mode the supervise prompt explicitly forbids state-mutating CLI commands and asks for a recommendation; in `supervised`/`autonomous` it may act per the contract.

### Phase 6 acceptance

- Blocking a task produces exactly one `engine.attention_needed` event.
- `meta/supervise` with a fake Claude subprocess: digest contains the blocked reason; turn persisted with `origin="supervision"`; duplicate call → 409.
- `directed` project: supervise prompt contains the no-mutation instruction (string assertion).

---

## Phase 7 — Transport polish and cleanup

### 7.1 SSE: stop hammering SQLite on a fixed interval (backlog item)

`dashboard_backend.py` stream loop polls the full sprint-events query every 0.5 s. Use SQLite's cheap change detector:

- In `ForemanStore`, add `data_version() -> int` returning `PRAGMA data_version` (changes when *another connection* commits — the stream holds its own connection, so engine writes are visible).
- Stream loop: each tick, read `data_version()`; only run `list_sprint_stream_messages` when it changed since the last fetch (or on the first iteration). Keep the heartbeat logic. Reduce `STREAM_POLL_INTERVAL_SECONDS` to 0.25 — the per-tick cost is now one pragma.
- Same optimization for the CLI `foreman watch` loop (it owns a store connection too).

### 7.2 `run_with_retry` duplicate-event note

On an `InfrastructureError` mid-stream, events from the aborted attempt were already yielded/persisted, and the retry replays the step. Persisted transcripts therefore can contain partial duplicates. Acceptable, but make it diagnosable: when retrying, emit the existing `agent.infra_error` event **and** ensure `retry_count` on the run record is actually incremented — today `Run.retry_count` is never written by the orchestrator. Fix: count `agent.infra_error` events seen during `_execute_native_runner_step` and set `run.retry_count` in `_complete_run`.

### 7.3 Documentation pass

- README: multi-model setup (env injection, config-dir isolation, OpenRouter-via-LiteLLM note), the tiered workflow, judge settings, executor overrides, supervision endpoint.
- `AGENTS.md`: nothing (worker-facing rules unchanged).
- CHANGELOG entries per phase.
- `docs/adr/ADR-0006-multi-model-fleet-via-env-injection.md` and `ADR-0007-tiered-review-and-llm-judged-evidence.md` capturing the decisions at the top of this spec (reuse harnesses; judge as direct HTTP; ladder on step visits).

---

## Appendix A — Migration ledger added by this spec

| # | Phase | Contents |
|---|-------|----------|
| 11 | 2 | `meta_sessions`, `meta_turns` + index |
| 12 | 3 | `tasks.executor_overrides_json`, `tasks.complexity` |

Append-only; never renumber. Update `tests/test_migrations.py` integrity checks.

## Appendix B — New/changed project settings

| Setting | Default | Phase | Meaning |
|---|---|---|---|
| `meta_agent_model` | `""` | 2 | `--model` for the manager session |
| `judge_base_url` / `judge_model` / `judge_api_key_env` | unset | 4 | criteria judge endpoint; unset → heuristic |
| `judge_max_diff_chars` | 24000 | 4 | diff cap fed to the judge |
| `review_diff_max_chars` | 16000 | 5 | diff cap in reviewer prompts |

Add all of them to `foreman/settings.py` (`ProjectSettings.from_raw`) with validation, since that module is the declared owner of settings shape.

## Appendix C — Validation checklist (run after every phase)

```bash
./venv/bin/pip install -e . --no-build-isolation
./venv/bin/python -m unittest discover -s tests -v
./venv/bin/foreman --help && ./venv/bin/foreman roles && ./venv/bin/foreman workflows
./venv/bin/python scripts/validate_repo_memory.py
npm --prefix frontend test && npm --prefix frontend run build   # only when API payloads changed
```

Sprint sizing suggestion for repo memory: Phase 0 = one sprint ("correctness-fixes"); Phases 1–3 = one sprint each; Phase 4+5 may share a sprint ("token-economy"); Phases 6 and 7 = one sprint each. Archive per the existing sprint-memory conventions.