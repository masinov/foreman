# PR Summary: feat/task-add-the-policy-matrix-triage-plan-merge-and-notification-decisions-v2

## Summary

- Sprint 54 slice 4 (the CHANGELOG numbers by landing order, where it is the
  sixth). Autonomy in Foreman is now a **policy, not a mode**: one matrix
  decides every question of the form "does a person do this?".
- New `foreman/policy.py` owns four decisions — `triage`, `plan_approval`,
  `merge_approval`, `notification` — each resolved from three layers, most
  specific first: **the task's override**, then **a rule for the task's type**
  (`policy_rules`), then **the project default**, else the built-in.
- Resolution reports **where** each value came from, and every task's first
  step records one `policy.resolved` event carrying all four `(value, source)`
  pairs — so the audit trail answers *why* a person was or was not asked.
- New task status **`triage`**: work filed through the intake API waits there
  until a person accepts it, unless the project's triage policy says `auto`.
  The engine never selects a `triage` task.
- Gate behaviour is unchanged for a project that sets nothing new.
  `_gate_policy_decision` now delegates to the matrix instead of reading
  settings itself, but the settings names, the defaults, the
  `executor_overrides.gates` shape, `workflow.gate_auto_approved`, and the
  `human_gate_decisions` rows are all identical.

### Numbering note

The task specified **ADR-0013**. That number was taken by the intake endpoint
slice that landed on `main` before this branch started, so this decision is
**ADR-0014**. Nothing else about the task's scope changed.

## Scope

In:

- `foreman/policy.py`: the decisions, their vocabularies, defaults, resolution,
  and serialization,
- `policy_rules` / `triage` / `notification` settings validation, and
  `executor_overrides.policy`,
- the `triage` task status everywhere statuses are enumerated,
- the orchestrator's gate delegation, `policy.resolved`, and the `notify` field,
- `GET /api/projects/{id}/policy`, `POST /api/tasks/{id}/accept`,
  `foreman task accept`, `foreman task override --triage/--notification`, and
  the policy matrix in `foreman config`,
- the board's triage column and Accept, the drawer's Policy section, and the
  settings panel's defaults + rules editor,
- docs, ADR, and tests.

Out (later tasks, per the task description):

- **notification delivery.** The resolved value is recorded on the events it
  would announce; no channel acts on it yet.
- per-user identity, which would let a policy name *which* person.

## Files changed

New:

- `foreman/policy.py` — the matrix: `POLICY_DECISIONS`, `POLICY_VALUES`,
  `POLICY_DEFAULTS`, `PolicyDecision`, `PolicyMatrix`, `describe_resolution`.
- `tests/test_policy.py` — 27 tests.
- `docs/adr/ADR-0014-autonomy-as-policy.md`.

Changed:

- `foreman/settings.py` — `triage`, `notification`, `policy_rules` fields;
  `_validate_policy_default` and `_validate_policy_rules` replace
  `_validate_gate_policy`.
- `foreman/models.py` — `triage` in `TaskStatus`/`TASK_STATUSES`;
  `executor_overrides.policy` validated; `GATE_POLICY_NAMES` derives from
  `policy.GATE_DECISIONS`.
- `foreman/store.py` — new `has_event(task_id=, event_type=)`; `triage` in the
  branch-match status ordering.
- `foreman/orchestrator.py` — `_gate_policy_decision` delegates to the matrix;
  new `_notification_policy` and `_emit_policy_resolved`; `notify` on
  `engine.attention_needed` and `workflow.paused`.
- `foreman/dashboard_service.py` — intake applies the triage policy and emits
  the attention turn; `accept_task`; `get_project_policy`; `policy` on the task
  payload.
- `foreman/dashboard_backend.py` — the policy and accept routes.
- `foreman/cli.py` — `task accept`; `--triage`/`--notification` on
  `task override`; the policy matrix in `config`; `triage` in the board and the
  count lines.
- `frontend/src/{App,components}.jsx`, `api.js`, `format.js`, `styles.css` —
  the triage column, Accept, the drawer's Policy section, `PolicyMatrixSection`.
- `foreman/dashboard_frontend_dist/` — rebuilt.
- `docs/MANUAL.md` (§14 rewritten as the policy matrix, §25 triage, the CLI
  reference, the endpoint map, the settings table, the Task model),
  `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`.
- `tests/test_cli.py`, `tests/test_store.py`, `tests/test_intake.py`,
  `tests/test_workflow_gates.py` — see Tests.

## Migrations

**None.** `tasks.status` is a text column, so `triage` needs no schema change,
and settings are a JSON blob, so the three new keys need none either. The task
asked to stop and explain if a migration were required; it was not.

## Risks

- **A new task status is a vocabulary change every consumer sees.** Adding
  `triage` to `TASK_STATUSES` widens every `task_counts` dict, which is why
  four existing assertions changed. The mitigation is that no consumer indexes
  statuses positionally: counts are built from `TASK_STATUSES`, the CLI board
  and the React board enumerate columns, and `select_next_task` selects `todo`
  explicitly rather than excluding terminal states — so a `triage` task is
  invisible to the engine without any change to selection.
- **Gate resolution moved.** The old function read settings inline; the matrix
  now answers. Covered by the pre-existing gate suite unchanged (auto approves
  and merges, human pauses and resumes, a per-task `gates` override still wins)
  plus a new test that a task-type rule can decide the same gate.
- **Lenient reads can mask a bad value.** A stored policy the matrix does not
  recognize is silently dropped for the built-in default. This is deliberate —
  a hand-edited row must not stop a run — and the exposure is bounded by
  `ProjectSettings` refusing the same value on write, so the only way to reach
  it is editing SQLite directly.
- **`policy.resolved` is written once per task**, guarded by a store query
  rather than an in-memory flag, so it survives resumes and process restarts.
  The cost is one indexed `EXISTS` per step; events are already indexed by
  `task_id`.
- **Intake now parks work by default.** A project that was relying on filed
  work being immediately runnable (intake landed one slice ago, so this is a
  narrow window) must set `triage=auto`. Documented in MANUAL §25 and in the
  CHANGELOG.

## Tests

```
./venv/bin/python -m unittest discover -s tests     # 935 tests, OK (1 skipped)
npm --prefix frontend test                          # 48 tests, 4 files, passed
npm --prefix frontend run build                     # built, dist committed
./venv/bin/python scripts/validate_repo_memory.py   # passed
```

`tests/test_policy.py` (27 tests): the built-in defaults and that every
decision has one; the gate decisions are a subset of the matrix; an unknown
decision raises; the full precedence chain (override > rule > project >
built-in) including that a rule only covers the decisions it names, that
`policy` beats `gates`, and that `gates` never decides a non-gate decision;
lenient reads (an invalid stored value, a half-malformed rules object, `None`
settings, an invalid override); the two serializations; and strict validation
in `ProjectSettings` and `validate_executor_overrides`.

`tests/test_workflow_gates.py` (+4): a task-type rule decides the merge gate;
the first step records `policy.resolved` with all four decisions and their
sources, on the `develop` run, exactly once even across a gate resume; a paused
gate carries the resolved `notify` with the rest of its payload untouched; and
`task override` takes `--triage`/`--notification`, rejects bad values, clears
one override with an empty value, and coexists with `--gate`.

`tests/test_intake.py` (+22): the default policy parks filed work in `triage`
and `triage=auto` queues it; a task-type rule beats the project default; a
triaged task raises exactly one attention turn carrying `notify` and an `auto`
one raises none; the intake event records the status and the decision; accept
moves it to `todo` and refuses a task that is not in triage; the engine selects
nothing until it is accepted. Plus the policy endpoint (project view, `task_id`
resolution, the task payload's `policy`, a task from another project refused,
both shapes over the real route) and the settings endpoint accepting and
refusing the new settings. Plus the CLI: accept, refusal, cancel from triage,
the board's triage section appearing only when occupied, and `config` printing
the matrix and refusing a malformed `policy_rules`.

Frontend (+10): the drawer's Policy section renders each decision with its
source (and nothing when the payload carries none); `TaskCard` offers Accept
only in `triage`; `PolicyMatrixSection` shows the four defaults falling back to
the built-ins, writes a change back, adds a rule row and edits one decision on
it, and drops a row when its last decision is cleared; the board hides the
triage column until work is waiting and otherwise renders it with a working
Accept.

Four pre-existing assertions changed, all of them the widened status
vocabulary: two `task_counts` dicts in `tests/test_store.py`, three count lines
and one board progress line in `tests/test_cli.py`, and the intake test that
asserted filed work lands in `todo` — which is exactly the behaviour this slice
changes, so it now asserts `triage` and the auto path is covered separately.

No test invokes a real `claude` or `codex` binary: the policy tests are pure,
the intake tests file a task and return, and the orchestrator tests drive a
scripted runner.

## Screenshots or output examples

```console
$ foreman config demo --set 'policy_rules={"docs": {"merge_approval": "auto", "notification": "none"}}'
Updated config
Project: demo | Demo
Changed: policy_rules={"docs": {"merge_approval": "auto", "notification": "none"}}
Settings:
- policy_rules={"docs": {"merge_approval": "auto", "notification": "none"}}
...
Policy matrix:
- triage=human (default)
- plan_approval=human (default)
- merge_approval=auto (default)
- notification=attention (default)
Policy rules:
- docs: merge_approval=auto notification=none

$ curl -X POST localhost:8000/api/projects/demo/intake -H "Authorization: Bearer fmn_..." \
    -d '{"title":"Disk full on web-3","task_type":"fix",
         "source":{"system":"pagerduty","external_ref":"INC-42"}}'
HTTP 201  {"id": "task-disk-full-on-web-3", "status": "triage", "created": true}

$ curl localhost:8000/api/projects/demo/policy?task_id=task-disk-full-on-web-3
{
  "resolution": {
    "triage":         {"value": "human",     "source": "built_in_default"},
    "plan_approval":  {"value": "human",     "source": "built_in_default"},
    "merge_approval": {"value": "auto",      "source": "built_in_default"},
    "notification":   {"value": "attention", "source": "built_in_default"}
  }
}

$ foreman board demo
Sprint: demo-intake | Intake queue
Progress: done=0/1 | in_progress=0 | blocked=0 (gate=0 engine=0) | todo=0 | triage=1 | cancelled=0
Triage (1)
- task-disk-full-on-web-3 | fix | Disk full on web-3
Todo (0)
- none

$ foreman task accept task-disk-full-on-web-3
Accepted task
Task: task-disk-full-on-web-3 | Disk full on web-3
Status: todo

$ foreman task accept task-disk-full-on-web-3
Task task-disk-full-on-web-3 is not in triage (status: todo); only tasks awaiting triage can be accepted.

$ foreman task override task-disk-full-on-web-3 --triage auto --notification all --gate merge_approval=human
Updated task executor overrides
Overrides: {"gates": {"merge_approval": "human"}, "policy": {"notification": "all", "triage": "auto"}}
```

Dashboard: the board grows a **Triage** column (only when work is waiting
there) whose cards carry an **Accept** button; the task drawer gains a
**Policy** section listing each decision with the layer that decided it
(`merge approval  auto (task type rule: docs)`); the settings panel gains a
**Policy Matrix** section with the four defaults and a task-type rules grid.

## Acceptance criteria satisfied

- ✅ `foreman/policy.py` resolves all four decisions as override > task-type
  rule > project default; `ProjectSettings` validates `policy_rules`, `triage`,
  and `notification`.
- ✅ Intake lands in `triage` under `human` and `todo` under `auto`;
  `foreman task accept` moves it on; the engine never selects `triage`.
- ✅ Gate behaviour unchanged for projects that set nothing new;
  `executor_overrides.gates` still works; `workflow.gate_auto_approved` and the
  gate decision records keep their shape.
- ✅ Every task's first step records `policy.resolved` with all four decisions
  and their sources.
- ✅ `GET /api/projects/{id}/policy` (with optional `task_id`); the settings
  endpoint and `foreman config` accept the new settings; `task override` takes
  `--triage` and `--notification`.
- ✅ The dashboard shows the triage column with Accept, the policy defaults and
  rules in settings, and the resolved policy in the drawer; bundle rebuilt.
- ✅ All four validation commands pass.
- ✅ `docs/MANUAL.md`, `README.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, the
  ADR (as 0014), and this PR note are updated.

## Follow-ups

- **Notification delivery.** The resolved value is recorded and nothing reads
  it. The next slice needs channels (webhook, email, chat) and a per-project
  destination; `notify` on `engine.attention_needed` and `workflow.paused` is
  the seam it should consume.
- **Ageing the triage queue.** Nothing prunes or escalates work that sits in
  `triage` indefinitely. A stale-triage attention turn would be the natural
  addition once notification delivery exists.
- **Per-user identity.** A policy can say a person is required but not *which*
  person; that needs the Phase 1 identity work that also replaces the
  dashboard's shared token.
