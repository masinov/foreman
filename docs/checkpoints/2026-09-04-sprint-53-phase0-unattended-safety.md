# Checkpoint: sprint-53-phase0-unattended-safety

## What works

- An unattended `foreman run` on one machine no longer hangs on a silent
  agent, leaks the agent's process group, or leaves a run row `running`
  after a stop: `foreman/runner/process.py` pumps streams, ticks on silence,
  kills process groups, and drains children on SIGTERM, SIGINT, and exit.
- The engine, dashboard, and CLI share one SQLite file in WAL mode with a busy
  timeout and retrying hot writes; migrations apply atomically; retention and
  deletes honor every foreign key; task keys are unique by sequence.
- The role contract is read from the agent's final message; reviewer
  outcomes, review kinds, and signal allowlists are declared in TOML.
- Every workflow tests before it reviews and ends in a `merge_approval` gate
  governed by policy (`merge_approval`, `plan_approval`, per-task overrides).
- The dashboard is loopback-only by default, token-protected off-loopback,
  CORS-allowlist-only, and keeps the manager chat off the network.
- 605 backend tests and 18 frontend tests pass; the dogfood database
  upgrades in place.

## What is incomplete

- The engine is still one-shot; nothing consumes tasks that arrive later
  (Phase 1: `foreman serve`).
- No intake endpoint, no policy matrix beyond the merge and plan gates, no
  planner step, no worktree isolation, no pull-request integration, no
  identity beyond the shared token, no notifications (all Phase 1).
- Per-task leases remain although a single engine lock would be safer; the
  session key still ignores model and endpoint; infrastructure retry is not
  session-aware.

## Known regressions

- None known. Behavior changes are documented per slice in `CHANGELOG.md`:
  retention opt-in, invalid settings refuse to run, SIGINT handled by
  `foreman run`, workflow order, `merge_approval` run rows, token-gated API,
  git-repository requirement on project creation.

## Schema or migration notes

- Migration 14 rebuilds `human_gate_decisions` and `decision_gates` with
  `ON DELETE` rules, adds `idx_events_task`, `projects.task_key_seq`, and a
  unique partial index on `(project_id, task_key)` after blanking duplicate
  keys. Verified against a copy of the repository's own database.

## Safe branch points

- `main` at the sprint-53 close (slice 6 fast-forwarded): Phase 0 complete,
  full suite green, repo-memory validation clean.
