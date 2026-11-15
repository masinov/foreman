# PR Summary: feat/agent-sandbox-first-cut

## Summary

- Sprint 59, slice 7. What an agent is handed is narrowed: its tools, its
  environment and its connectors. ADR-0023.

## Scope

- `AgentRunConfig.allowed_tools`, from the role's `[agent.tools] allowed`.
  Claude: `--tools`. Codex: a command or file change outside the list is
  declined.
- `code_reviewer` and `security_reviewer`: `allowed = ["Read", "Grep",
  "Glob"]`.
- `runner.env.agent_environment`: the agent's whole environment is a short
  list of host variables plus the role's `[agent.env]` and the project's
  `agent_env_passthrough` (new host-level setting). `popen_kwargs` gained
  `inherit_env`.
- Claude runner: `--strict-mcp-config` unless the role sets
  `strict_mcp_config = false` under `[agent.flags]`.
- `engine.role_policy` events carry `allowed_tools`.
- The correction sent after an unread approval (slice 6) now also says: if
  you cannot open files, do not approve a change you have seen only part
  of. The two prompt-only reviewers have no reading tools.

## Files changed

- `foreman/runner/{base,env,process,claude_code,codex}.py`
- `foreman/engine/{agent_step,workflow_runner,output_contract}.py`
- `foreman/settings.py`, `foreman/data/roles/{code,security}_reviewer.toml`
- `frontend/src/pages/settings/settingsWords.js`
- `tests/test_agent_sandbox.py` (new), `tests/test_runner_{claude,codex,env}.py`
- `docs/adr/ADR-0023-agent-sandbox-first-cut.md`, `docs/adr/README.md`,
  `docs/MANUAL.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- A project whose agents relied on a variable from the engine's environment
  (a database address, a package index token) will find it gone until it is
  named in `agent_env_passthrough` or the role's `[agent.env]`.
- A developer agent can no longer use the engine's forge token or SSH agent.
  Intended, but it is a change.
- A role that relied on the operator's MCP connectors loses them until it
  names a configuration.
- This is not confinement: see "Not covered" in ADR-0023.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1385 tests, 5 skipped)
- frontend lint, tests and build
- One real call through `ClaudeCodeRunner` with the reviewer's settings
  (model `claude-haiku-5-5`, under one cent): before `--strict-mcp-config`
  the tool list was Glob, Grep, Read plus the operator's connectors; after,
  exactly Glob, Grep, Read. The call authenticated with the short
  environment.

## Screenshots or output examples

- `TOOLS ['Glob', 'Grep', 'Read']`

## Acceptance criteria satisfied

- The allowlist reaches both runners; shipped reviewers cannot write or run
  commands; the engine's secrets are not in an agent's environment; a
  project can pass named variables through.

## Follow-ups

- Isolated CLI settings (the agent still reads the operator's home), and a
  container per task (Phase 5).
