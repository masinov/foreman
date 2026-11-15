# PR Summary: feat/manager-session-read-surface

## Summary

- Sprint 59, slice 8 (FOR-42). The manager session can read and propose,
  and nothing else.

## Scope

- `meta_agent.manager_command`: `--permission-mode default`, `--tools
  Read,Grep,Glob,Bash,Write`, `--allowed-tools
  Read,Grep,Glob,Bash(foreman:*),Edit(.foreman/manager/**)`,
  `--strict-mcp-config`.
- `meta_agent.manager_process_env`: the short agent environment (ADR-0023)
  plus the session marks, with this installation's `foreman` first on the
  path.
- The operating contract: a proposal is written to
  `.foreman/manager/<name>.json` and passed with `--json <path>`. A
  reminder of this goes into every later turn.
- ADR-0022 amended with what the session can and cannot do, as observed.

## Files changed

- `foreman/meta_agent.py`
- `tests/test_meta_agent.py`
- `docs/adr/ADR-0022-manager-proposes-person-confirms.md`,
  `docs/sprints/current.md`, `docs/sprints/backlog.md`, `docs/STATUS.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- The confinement is the Claude Code CLI's: its permission rules and its
  judgement of which shell commands only read. Checked for version 2.1.325.
- The manager can no longer pipe or post-process `foreman` output in its
  shell, or read files outside the repository.
- A manager session begun before this change resumes under the new limits;
  the per-turn reminder tells it the new way to propose.
- In Foreman's own project FOR-42 is still in the backlog awaiting accept or
  decline; the work is done here by hand.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1388 tests, 5 skipped)
- frontend lint, tests and build (unchanged code)
- Real CLI, model `claude-haiku-5-5`, a few cents in all: three probes with
  a fake `foreman` on the path (results in the ADR table), and one real
  manager turn through `process_message` on a copy of the database, which
  wrote a draft, ran `foreman proposal create` and produced a stored
  proposal.

## Screenshots or output examples

- `{'type': 'proposal', 'proposal_id': 'prop-20261115185739325735-0273b779'}`

## Acceptance criteria satisfied

- FOR-42: "cannot edit files or write the database except through `foreman
  proposal create`" (one exception, stated: its own drafts folder); "tested
  with a fake executable that records its arguments"; "ADR-0022 updated".

## Follow-ups

- Manager chat through the engine's runner with per-user sessions and cost
  per turn (Phase 5).
