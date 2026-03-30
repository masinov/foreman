# Checkpoint: human-gate-resume

## What works

- paused `_builtin:human_gate` tasks can be approved or denied through
  `foreman approve --db <path>` and `foreman deny --db <path>`
- human decisions are persisted as runs plus `workflow.resumed` events
- executor-backed orchestrator calls can continue from the paused workflow step
  immediately instead of restarting from workflow entry
- bootstrap CLI approvals and denials persist the exact next step and carried
  output when native runners are not available yet

## What is incomplete

- the CLI still cannot execute Claude-backed or Codex-backed next steps
  directly because native runner integration has not landed
- `foreman run` remains a stub, so deferred resume is mainly exercised through
  the orchestrator API and future runner work

## Known regressions

- none identified in the current automated coverage

## Schema or migration notes

- no schema changes were required; human-gate resume reuses
  `tasks.workflow_current_step` and `tasks.workflow_carried_output`

## Safe branch points

- `feat/human-gate-resume` after human-gate resume tests and repo-memory
  rollover
