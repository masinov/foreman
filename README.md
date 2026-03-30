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

The implementation has not started in earnest yet. What exists today is:

- the product spec,
- the UI mockup,
- two supervised autonomous entry points in `scripts/`,
- repo-memory docs that tell the next agent what to build next.

The immediate goal is to use this scaffold to start implementing the first
Foreman runtime slices without carrying over the previous project's identity or
assumptions.

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

The repo is primed for the first real engineering sprint. The next recommended
task is:

- bootstrap the Python package, `pyproject.toml`, CLI entrypoint, and initial
  smoke tests for the `foreman` package.

That task is already recorded in `docs/sprints/current.md` so a fresh agent can
start without additional instructions.

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
