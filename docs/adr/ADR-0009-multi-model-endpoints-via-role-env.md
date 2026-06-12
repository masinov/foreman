# ADR-0009: Multi-Model Endpoints Via Role Environment

- Status: accepted
- Date: 2026-06-12

## Context

Foreman needs to run cheaper worker models such as MiniMax M3 without adding a
new model-specific runner. Claude Code can already talk to Anthropic-compatible
endpoints when the right environment is present, and the accepted runner
contract already treats Claude Code as the native harness for Claude-like
agents.

The review roadmap also explicitly rules out parallel worker pools and
multi-worktree execution for this phase. The requirement is model and endpoint
selection, not concurrent execution.

## Decision

Role TOML may define an optional `[agent.env]` table. Foreman resolves that
table immediately before one native runner invocation and passes the resolved
environment to the runner process.

Supported value forms:

- `literal` values are passed through unchanged.
- `env:NAME` reads a required host environment variable and fails preflight if
  it is missing.
- `env:NAME?fallback` reads a host environment variable or uses a literal
  fallback.
- Keys ending in `_DIR` or `_PATH` are expanded with `os.path.expanduser`.

Resolved secrets are never persisted. The raw role env specification remains
in TOML; run records and events store only normal runner telemetry.

Claude Code remains the harness for Anthropic-compatible third-party endpoints.
Roles that point at different endpoints should use distinct `CLAUDE_CONFIG_DIR`
values so resumed sessions do not mix provider state.

This ADR does not introduce worker pools, parallel execution, or multi-worktree
execution. The orchestrator continues to execute one workflow step at a time.

## Consequences

- MiniMax M3 and similar endpoints can be configured through role files instead
  of new runner implementations.
- Missing required endpoint secrets surface as one explicit preflight failure
  and consume no infrastructure retries.
- Existing roles without `[agent.env]` preserve their current process
  environment behavior.
- Endpoint-specific session isolation is operator-configured through role env,
  not enforced by Foreman.
