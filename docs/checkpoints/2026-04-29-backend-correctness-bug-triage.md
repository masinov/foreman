# Backend Correctness Bug Triage — 2026-04-29

## Context

An untracked diagnostic note listed several backend hardening bugs as still
present on `main`. The note was useful, but it lived under `docs/specs/`,
which is reserved for product direction. This checkpoint preserves the
diagnostic result as repo memory without treating it as an authoritative spec.

## Triage Result

Several listed issues were already fixed on `main` before this branch:

- standard, secure, and architect workflows route merge conflicts back to
  development before another review cycle
- merge-time completion guard blocks implementation tasks without material
  deltas, failed proof status, missing code-review approval, or missing
  security approval in secure workflows
- completion evidence records reviewer outcomes, security-review outcomes,
  structured criterion entries, proof status, and failure reasons
- crash-recovery event constructors no longer accept or persist lease tokens
- lease acquisition computes monotonic fencing tokens and catches active-lease
  uniqueness races
- branch-violation events are emitted when task-branch or default-branch
  invariants fail
- autonomous placeholder tasks are checked for `signal.task_started` only
  after the first developer step has a chance to emit it, with persisted
  title, branch, and criteria accepted after restart

## Fixed In This Branch

- Immediate streamed builtin events now persist `schema_version`, matching the
  delayed builtin event path.
- Regression tests now assert that unknown agent outcomes normalize to `error`.
- Regression tests now assert that informal reviewer approvals (`yes`, `lgtm`,
  `pass`) do not approve a merge path.
- Crash-recovery event tests now assert lease tokens are redacted from durable
  event payloads.
- Lease tests now assert the unique active-resource index exists and fencing
  tokens increment across released or expired lease reacquisition.
- The old lease migration test now simulates a pre-migration database by
  removing all migration rows from version 6 onward, instead of deleting only
  version 6 while later versions kept `schema_version()` high.
- Merge conflicts now return the explicit `conflict` outcome so workflow
  `completion:conflict` transitions are actually reachable.
- Directed conflict recovery now checks out the task branch again when the
  aborted merge leaves a clean worktree on `main`.
- Reviewer and security-reviewer outcomes are routed through reviewer-decision
  normalization, preserving strict unknown agent outcomes without turning
  `approve` into a generic agent error.
- Completion proof status now accepts small real diffs when tests pass and code
  review explicitly approves, so heuristic criteria matching misses do not
  deadlock otherwise valid supervised runs.

## Remaining Follow-Up

Settings validation exists in `foreman/settings.py`, but runtime paths still
read some raw `project.settings` values directly. The next backend slice should
centralize project-settings parsing at orchestration and executor boundaries so
invalid persisted settings fail deterministically instead of being silently
defaulted by local helper functions.
