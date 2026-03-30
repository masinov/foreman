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
- a SQLite-backed store baseline with typed models for projects, sprints,
  tasks, runs, and events,
- shipped declarative `roles/*.toml` and `workflows/*.toml` definitions,
- TOML loaders plus prompt rendering and workflow transition validation,
- an orchestrator loop that can move a persisted task through the shipped
  development workflow with built-in test, merge, and mark-done steps,
- a working `foreman init --db <path>` path that scaffolds `AGENTS.md`,
  `docs/adr/`, `.foreman/`, and `.gitignore` updates in a target repo while
  persisting or updating the project in SQLite,
- runtime context projection into `.foreman/context.md` and
  `.foreman/status.md` before agent steps and after task completion,
- human-gate `foreman approve --db <path>` and `foreman deny --db <path>`
  commands that persist explicit approval or denial decisions and resume the
  workflow from the paused step instead of restarting from entry,
- deferred human-gate resume persistence for agent-backed next steps when the
  required native backend or repo runtime is unavailable, while still
  recording the next workflow step and carried output in SQLite,
- shared native runner primitives plus the first Claude Code stream-json
  backend in `foreman/runner/`,
- a native Codex JSON-RPC backend in `foreman/runner/` with thread resume,
  structured event mapping, and automatic tool-approval responses,
- native orchestrator execution for shipped Claude-backed roles, including
  retry normalization, session reuse for persistent developer roles, and
  structured runner event capture,
- native orchestrator execution for Codex-backed roles, plus immediate
  human-gate resume when the next native backend and repo are available,
- an accepted runner contract ADR in
  `docs/adr/ADR-0001-runner-session-backend-contract.md`,
- git execution helpers and integration coverage for workflow transitions,
- scaffold, smoke, integration, and round-trip tests for the CLI shell and
  store,
- repo-memory docs that point the next slice at dashboard implementation.

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

- build the first dashboard implementation aligned to
  `docs/mockups/foreman-mockup-v6.html` while honoring
  `docs/adr/ADR-0001-runner-session-backend-contract.md`.

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
./venv/bin/python -m unittest tests.test_runner_codex tests.test_runner_claude tests.test_orchestrator -v
./venv/bin/foreman --help
./venv/bin/foreman projects
./venv/bin/foreman status
./venv/bin/foreman roles
./venv/bin/foreman workflows
./venv/bin/foreman approve --help
./venv/bin/foreman deny --help
./venv/bin/foreman projects --db /tmp/foreman.db
./venv/bin/foreman status --db /tmp/foreman.db
```
