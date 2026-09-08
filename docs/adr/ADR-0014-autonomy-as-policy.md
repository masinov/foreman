# ADR-0014: Autonomy As Policy

- Status: accepted
- Date: 2026-09-08
- Deciders: engine team

> The sprint task named this ADR-0013. That number was taken by the intake
> endpoint slice that landed first, so this decision is ADR-0014. Nothing else
> about the task changed.

## Context

Foreman decides where a person is required in two unrelated places, and neither
of them scales past the two decisions that already exist.

The workflow gates are settings: `merge_approval` and `plan_approval` are
project-wide strings resolved by `ForemanOrchestrator._gate_policy_decision`
from a per-task `executor_overrides.gates` entry, then a setting of the same
name, then a hard-coded default. Everything else that needs a person is not a
policy at all — it is a code path. Intake (ADR-0013) has to choose whether
filed work is immediately runnable, and the answer today would be whatever the
intake code hard-codes. Notification, when its channels land, would be a third
independent mechanism.

That shape fails on three counts:

1. **It is project-wide.** A team that wants a person on every `feature` merge
   and none on a `docs` typo fix has to choose one of the two, or override
   every task by hand. Autonomy is not uniform across a project's work.
2. **It is not auditable.** The engine records *that* a gate was auto-approved
   (`workflow.gate_auto_approved`, a `policy:<name>` decision row), but not
   *why* — which layer decided, and what the alternative was. When a merge goes
   through unattended, "the setting said so" is not a satisfying answer at
   review time.
3. **It does not generalize.** Each new decision that needs a human would add
   its own setting, its own resolution code, and its own precedence rules. By
   the fourth one, no two behave the same way.

Phase 1 of the production readiness review states the requirement directly:
autonomy must be a *policy*, not a mode.

## Decision

**One matrix decides every question of the form "does a person do this?"**

`foreman/policy.py` owns four decisions — `triage`, `plan_approval`,
`merge_approval`, `notification` — each with its own value vocabulary
(`auto`/`human` for the first three, `none`/`attention`/`all` for the fourth)
and its own built-in default (`human`, `human`, `auto`, `attention`).

**Three layers, resolved most specific first.**

1. the task's `executor_overrides` (`policy`, or the older gate-only `gates`),
2. a rule for the task's type, from the `policy_rules` project setting,
3. the project default setting for that decision, else the built-in.

Nothing else may resolve a policy. `_gate_policy_decision` delegates to the
matrix rather than reading settings; intake asks the matrix for `triage`; the
notification value is stamped onto the events that would carry it.

**Resolution reports its source, and the source is persisted.** A resolved
decision is a `(value, source)` pair, where source names the layer
(`task_override`, `task_type_rule` plus the type, `project_default`,
`built_in_default`). Every task's first step writes one `policy.resolved` event
holding all four pairs, so the audit trail answers *why* a person was or was
not asked, not only whether one was.

**Reads are lenient; writes are strict.** `ProjectSettings` refuses an unknown
task type, decision, or value at the point of writing, so a typo fails at
`foreman config` rather than silently at run time. `PolicyMatrix.from_settings`
does the opposite: a stored value it does not recognize is dropped and the
built-in default applies. A row written before a validator existed, or edited
by hand, must not be able to stop a run.

**`triage` is a task status, not a flag.** Work filed by another system under a
`human` triage policy lands in a new `triage` status, where `select_next_task`
will not see it, until `foreman task accept` (or the board's Accept) moves it
to `todo`. Modelling it as a status rather than a boolean means every existing
consumer — the board, the counts, cancel, the dashboard — handles it by
enumerating statuses, which they already do.

## Consequences

- Autonomy is configured in one place with one precedence rule, and a fifth
  decision is a new entry in `POLICY_VALUES` plus a default, not a new
  subsystem.
- A project can be autonomous for `docs` and supervised for `feature` without
  touching a single task.
- The audit trail explains its own decisions. `policy.resolved` is written once
  per task, so resuming a paused task does not re-record what a reader has
  already seen.
- No migration was needed: `status` is a text column and settings are JSON.
- Existing projects are unaffected. The two gate settings keep their names,
  their defaults, and the `executor_overrides.gates` shape; `triage` only
  affects tasks filed through intake; `notification` only adds a `notify` field
  to events that were already emitted.
- This ADR records the decision model only. Notification *delivery* — the
  channels that act on the resolved value — is a later slice; the value is
  recorded on `engine.attention_needed` and `workflow.paused` so that slice has
  something to read.
