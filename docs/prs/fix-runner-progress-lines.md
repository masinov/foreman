# PR Summary: fix/runner-progress-lines

## Summary

Sprint 54 live-run fix, found while the engine ran slice 1 on itself. The
current Claude Code CLI streams `{"type":"system","subtype":"thinking_tokens"}`
counters about twice a second while the model reasons, plus
`rate_limit_event` notices. `ClaudeCodeRunner` mapped every unrecognized
line to a persisted `agent.tool_use` with tool `claude.stream_event` and
also persisted the raw line, so four minutes of one developer step wrote
roughly 400 event rows and 550 KB. Tool results (`user` lines) were
persisted twice with their full text, up to 26 KB per row.

## Scope

- `foreman/runner/claude_code.py`: lines are decoded once and classified
  before anything is persisted. Progress-only lines (`system` subtypes in
  `_PROGRESS_SYSTEM_SUBTYPES`, `rate_limit_event` with status `allowed`)
  become `agent.tick` heartbeats, which still drive the lease heartbeat and
  the time and cost gates but are never persisted. `system`/`init` becomes
  `agent.session` (session id, model, cwd, permission mode, tool count).
  `user` tool results become `agent.tool_result` (tool use id, `is_error`,
  full length, a 500-character preview, `truncated`). Rate-limit notices
  with any other status become `agent.rate_limit`. Raw lines are capped at
  `RAW_LINE_MAX_CHARS` (8,000) with `truncated` and `length` when cut.
  Unknown message types are kept as raw output only instead of being
  reported as a tool use.
- `docs/MANUAL.md` §19 event taxonomy, `CHANGELOG.md`, `docs/STATUS.md`.

## Files changed

- `foreman/runner/claude_code.py`, `tests/test_runner_claude.py`
- `docs/MANUAL.md`, `CHANGELOG.md`, `docs/STATUS.md`,
  `docs/prs/fix-runner-progress-lines.md`

## Migrations

- none

## Risks

- Consumers that counted `agent.tool_use` rows as activity will see fewer
  rows; the CLI and frontend summaries only special-case `command`,
  `file_change`, and `message`, so nothing shipped depends on the old shape.
- Raw lines longer than 8,000 characters lose their tail in the transcript.
  The content they carried is either the agent's own text (kept in full in
  `agent.message`) or a tool result (kept as a preview, and for file edits
  in git).
- The Codex runner is untouched; it has its own message taxonomy.

## Tests

- `tests/test_runner_claude.py`: +3 (progress lines become ticks with no raw
  output, init and tool-result mapping with raw-line capping, non-allowed
  rate-limit notices persisted).
- `./venv/bin/python -m unittest discover -s tests` and
  `scripts/validate_repo_memory.py` (run on `main` after the merge).

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- a thinking phase no longer writes rows,
- tool results are bounded,
- no fake tool uses for unknown message types.

## Follow-ups

- Phase 1 backlog: raw output into its own capped and redacted table.
