# Checkpoint: 2026-06-12-minimax-worker-smoke

## What works

- `feat/worker-fleet-minimax-smoke` adds role-level `[agent.env]` resolution
  and runner env plumbing.
- Missing required env vars fail before runner launch with a single
  preflight-style `agent.error`.
- Existing roles without env preserve previous process-launch behavior.
- Host-side MiniMax M3 Claude Code smoke works:
  - simple `--print --model minimax-m3` returned `minimax-ok`.
  - edit-capable `--permission-mode bypassPermissions` run used `Write`,
    created `/tmp/foreman-minimax-smoke/minimax_smoke.txt`, and returned
    `TASK_COMPLETE`.

## What is incomplete

- The sandboxed Claude CLI environment did not see normal host auth/config and
  timed out in API retries with `apiKeySource: none`.
- `developer_worker` is not yet referenced by a workflow.
- Per-task model overrides and escalation ladders remain later review-roadmap
  work.

## Known regressions

- None found in focused validation.

## Schema or migration notes

- No SQLite migration.

## Safe branch points

- Branch: `feat/worker-fleet-minimax-smoke`
- Safe point: after focused runner, role, orchestrator, and CLI tests listed in
  `docs/prs/feat-worker-fleet-minimax-smoke.md`.
