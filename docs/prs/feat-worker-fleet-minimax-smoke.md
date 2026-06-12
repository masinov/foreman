# PR Summary: feat/worker-fleet-minimax-smoke

## Summary

- Adds the Phase 1 role environment seam needed to run MiniMax M3 and other
  Anthropic-compatible endpoints through the existing Claude Code runner.
- Verifies MiniMax M3 can perform a sequential edit-capable Claude Code run
  when invoked with the host-side configuration and `bypassPermissions`.

## Scope

- Role schema loading for optional `[agent.env]`.
- Runner config and process env plumbing for Claude Code and Codex.
- Orchestrator preflight behavior for missing required role env vars.
- Shipped `developer_worker` role example.
- README, architecture, ADR, sprint, status, and checkpoint documentation.

## Files changed

- `foreman/roles.py`
- `foreman/runner/base.py`
- `foreman/runner/env.py`
- `foreman/runner/claude_code.py`
- `foreman/runner/codex.py`
- `foreman/orchestrator.py`
- `roles/developer_worker.toml`
- `tests/test_runner_env.py`
- `tests/test_runner.py`
- `tests/test_runner_claude.py`
- `tests/test_runner_codex.py`
- `tests/test_roles.py`
- `tests/test_orchestrator.py`
- `tests/test_cli.py`
- `README.md`
- `CHANGELOG.md`
- `docs/ARCHITECTURE.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/adr/ADR-0001-runner-session-backend-contract.md`
- `docs/adr/ADR-0009-multi-model-endpoints-via-role-env.md`
- `docs/checkpoints/2026-06-12-minimax-worker-smoke.md`

## Migrations

- none

## Risks

- Host-side Claude/MiniMax configuration is required. In the sandboxed command
  environment, Claude reported `apiKeySource: none` and retried until timeout.
- `developer_worker` is an example role; workflows do not use it yet.
- Endpoint-specific session isolation is documented through `CLAUDE_CONFIG_DIR`
  rather than enforced by Foreman.

## Tests

- `./venv/bin/python -m unittest tests.test_runner_env tests.test_roles tests.test_runner tests.test_runner_claude tests.test_runner_codex -v`
- `./venv/bin/python -m unittest tests.test_orchestrator.ForemanOrchestratorTests.test_native_runner_resolves_role_env_before_execution tests.test_orchestrator.ForemanOrchestratorTests.test_missing_required_role_env_fails_once_without_runner_retry tests.test_cli.ForemanCLISmokeTests.test_roles_command_lists_shipped_roles -v`
- `./venv/bin/python -m unittest discover -s tests -v` — 513 tests passed.
- Manual host-side smoke: `timeout 90 claude --print --model minimax-m3 "Reply with exactly: minimax-ok"`
- Manual host-side edit smoke: `timeout 120 claude --print --verbose --output-format stream-json --model minimax-m3 --permission-mode bypassPermissions "..."`

## Acceptance criteria satisfied

- Role env resolution covers literal, required env, optional fallback, missing
  required, and path expansion cases.
- Runner tests prove merged env is passed only when configured.
- Orchestrator test proves missing required env fails once with
  `preflight_failed=true` and no runner retry.
- MiniMax M3 is verified through Claude Code for a sequential edit-capable run.

## Follow-ups

- Wire `developer_worker` into a tiered workflow or task override mechanism in
  the later model-selection sprint.
- Add dashboard affordances for role env visibility/editing only after deciding
  how secrets should be represented safely.
