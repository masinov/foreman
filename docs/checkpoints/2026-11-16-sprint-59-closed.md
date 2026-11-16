# Checkpoint: sprint 59 closed (2026-11-16)

The first sprint of Phase 5 of the finish plan is complete on `main`. It was
done by hand; the engine has been stopped since 2026-11-13.

## What works

- The engine defects found while Foreman ran sprint 58 are fixed, each with
  a test that fails without the fix: a run that came back without a turn is
  sent its prompt again; a resumed session's cost is counted once (the
  recorded runs were corrected, so sprint 58 reads $66.79, not $105.73); Run
  next takes effect when the task in hand finishes; an approved merge is
  carried out within about ten seconds while another task's step runs; the
  default branch is pushed after a merge when `merge_push_remote` names a
  remote.
- A reviewer's approval of a change it was shown only part of, with no file
  opened, is sent back once and then stops the task for a person.
- Agent sandbox, first cut (ADR-0023): a role's tool allowlist is passed to
  the agent CLI, the reading reviewers have Read, Grep and Glob, an agent
  process gets a short list of host variables and none of the operator's MCP
  connectors.
- The manager session reads the repository and runs `foreman` commands, and
  writes only its proposal drafts (FOR-42, ADR-0022 amendment). It can
  propose Mark done, Reopen, and a task's size and dependencies.
- A run on a task's Activity tab reads as sentences; a task's size, priority
  and dependencies can be changed after filing (`foreman task edit`, the
  Edit task dialog).
- Slices: `docs/sprints/archive/sprint-59-engine-left-running.md`.
- Validation at close: 1399 Python tests, 383 frontend tests, ESLint and
  `ruff check` clean, repository validator passing, CI green at `63ea8df`.

## What is incomplete

- None of the engine fixes has been seen in a run of the engine. The sandbox
  and the manager's confinement were checked with the real agent CLI; the
  cost fix, the no-turn retry, Run next, the merge during another step, the
  push and the reviewer rule are covered by tests only.
- An agent process still runs as the engine's user with a shell and the
  network. A container per task is not built.
- FOR-43 is not started. FOR-42 and FOR-43 wait in the backlog of Foreman's
  own project for the owner to accept or decline.
- The Phase 4 leftovers are unchanged: no browser acceptance pack, no types
  in the frontend, no markdown rendering.

## Known regressions

- None known.

## Schema or migration notes

- Migration 24: `runs.session_cost_usd`, and `cost_usd` of Claude Code runs
  rewritten as each run's own share of its session. Schema version 24.

## Safe branch points

- `main` at the merge of `docs/sprint-59-close`.

Next: the rest of Phase 5. A proposed sprint 60 is in
`docs/sprints/current.md`; it is not opened until the owner agrees its scope.
Whether to start the engine again is the owner's call.
