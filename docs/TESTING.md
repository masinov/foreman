# TESTING

## Principle

Foreman testing should verify durable workflow behavior, not just syntax.
Compilation-only checks are insufficient.

## Current baseline

The repo is still pre-implementation, so the current mandatory checks are
scaffold checks:

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`

## Expected testing layers once code lands

Unit tests:

- model validation
- SQLite store round-trips
- role and workflow parsing
- signal parsing
- git helper behavior that can be isolated

Integration tests:

- project initialization
- sprint and task lifecycle
- orchestrator transitions
- built-in test, merge, and human-gate steps
- context projection into `.foreman/`

Runner smoke tests:

- Claude Code runner wiring
- Codex runner wiring
- event capture and retry behavior

UI validation:

- manual checks against `docs/mockups/foreman-mockup-v6.html`
- project dashboard navigation
- sprint board interactions
- activity feed behavior

## Definition of done

Do not mark a task done unless:

- the relevant automated checks pass,
- new behavior is covered by tests when practical,
- user-visible changes include validation notes,
- the docs reflect the new reality.

If a slice cannot reasonably add tests yet, explain why in the PR summary and
record the follow-up explicitly.
