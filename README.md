# Foreman

Foreman is an autonomous development engine for turning a project spec into
reviewable implementation work through structured sprints, tasks, runs, and
human gates.

This repository is currently the bootstrap memory for that product. The only
authoritative product inputs are:

- `docs/specs/engine-design-v3.md`
- `docs/mockups/foreman-mockup-v6.html`

The rest of the repo exists to help agents start building Foreman cleanly from
those inputs.

## Key references

- Agent operating instructions: `AGENTS.md`
- Project status: `docs/STATUS.md`
- Current sprint: `docs/sprints/current.md`
- Backlog: `docs/sprints/backlog.md`
- Architecture baseline: `docs/ARCHITECTURE.md`
- Roadmap: `docs/ROADMAP.md`

## Current state

The bootstrap implementation has started. The repository now contains:

- the product spec,
- the UI mockup,
- two supervised autonomous entry points in `scripts/`,
- a first `foreman/` package scaffold with a runnable CLI shell,
- smoke tests for the initial CLI wiring,
- repo-memory docs that point the next slice at the SQLite store baseline.

The immediate goal is to keep turning this scaffold into the real Foreman
runtime without carrying over assumptions from the previous project.

## Autonomous entry points

Run all Python commands through the repo virtual environment:

```bash
./venv/bin/python scripts/reviewed_codex.py
./venv/bin/python scripts/reviewed_claude.py
```

What they do:

- `reviewed_codex.py` supervises a Codex development run against the current
  sprint docs and requests reviewer approval before accepting a completed slice.
- `reviewed_claude.py` does the same for Claude Code and is designed to keep
  moving through approved work until the backlog is exhausted.

Both wrappers expect these files to be current:

- `AGENTS.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/specs/engine-design-v3.md`
- `docs/mockups/foreman-mockup-v6.html`

## Next implementation slice

The next recommended task is:

- implement the SQLite model and store baseline for projects, sprints, tasks,
  runs, and events.

That task is already recorded in `docs/sprints/current.md`, so a fresh agent
can continue without additional instructions.

## Validation

Current scaffold validation:

```bash
./venv/bin/python scripts/validate_repo_memory.py
./venv/bin/python -m py_compile scripts/reviewed_codex.py
./venv/bin/python -m py_compile scripts/reviewed_claude.py
./venv/bin/python -m py_compile scripts/repo_validation.py
./venv/bin/python -m py_compile scripts/validate_repo_memory.py
```

As code lands, these checks should expand into real unit, integration, and UI
validation aligned to the spec.

Current code-level validation also includes:

```bash
./venv/bin/pip install -e . --no-build-isolation --no-deps
./venv/bin/python -m unittest discover -s tests -v
./venv/bin/foreman --help
./venv/bin/foreman projects
./venv/bin/foreman status
```
