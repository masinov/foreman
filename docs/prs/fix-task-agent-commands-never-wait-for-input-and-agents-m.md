# fix: agent commands never wait for input; AGENTS.md arrives once

## Summary
Sprint 63, ADR-0040 item 1 and ADR-0041 section 6. Every agent process gets a
no-op editor, plain pagers and no terminal credential prompt. `AGENTS.md` is
pasted into the prompt only when the backend would not load it itself.

## Scope
- `foreman/runner/env.py`: `NON_INTERACTIVE_ENV` applied in `agent_environment` (both runners); role `[agent.env]` wins.
- `foreman/engine/prompts.py`: `backend_loads_agents_md`, `repo_instructions_for_prompt`.
- `foreman/data/roles/developer.toml`: interactive programs are not available.
- `docs/ARCHITECTURE.md`: runner section.

## Files changed
See the diff; tests in `test_runner_claude.py`, `test_runner_codex.py`, `test_engine_prompts.py`.

## Migrations
None.

## Risks
- Claude Code's fallback to `AGENTS.md` when there is no `CLAUDE.md` was observed on 2.1.331 only. If a version drops it, such a repository gets no instructions; the virtualenv rule still comes through `environment_rules`.
- Codex was not checked live (sign-in revoked here); it is treated as loading `AGENTS.md` per its documentation, and its shell stdin is unverified.

## Tests
Touched modules plus the full suite; see the report.

## Acceptance criteria satisfied
All five. Deviation: Claude Code *without* a CLAUDE.md does not get a paste, because the real backend loads AGENTS.md there; a CLAUDE.md that lacks the import does.

## Follow-ups
Verify Codex stdin and AGENTS.md loading once its sign-in works.
