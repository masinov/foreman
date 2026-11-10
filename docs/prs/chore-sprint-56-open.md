# PR Summary: chore/sprint-56-open

## Summary

- Closes and archives sprint 55, opens sprint 56 (Phase 2, engine
  truthfulness), and refreshes the shipped role model ids.

## Scope

- `docs/sprints/current.md` (new sprint), sprint 55 archived, `docs/STATUS.md`.
- `roles/*.toml`: reviewers `claude-sonnet-5-5`, triage `claude-haiku-5-5`,
  architect and frontier reviewer `claude-opus-5-5`; manual table updated.

## Files changed

- `docs/sprints/*`, `docs/STATUS.md`, `docs/MANUAL.md`, `CHANGELOG.md`,
  `roles/architect.toml`, `roles/code_reviewer.toml`,
  `roles/frontier_reviewer.toml`, `roles/security_reviewer.toml`,
  `roles/triage_reviewer.toml`

## Migrations

- none

## Risks

- The new model ids were each accepted by the installed Claude Code CLI
  (2.1.322) in a one-word probe, except `claude-opus-5-5`, which was not
  probed.

## Tests

- `python -m unittest discover -s tests -p 'test_roles.py'`: pass
- `scripts/validate_repo_memory.py`: pass

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A fresh agent finds sprint 56 and its slices in `docs/sprints/current.md`.

## Follow-ups

- Sprint 56 slices.
