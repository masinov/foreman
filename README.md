# Foreman

Foreman is an autonomous development engine for turning a project spec into
reviewable implementation work through structured sprints, tasks, runs, and
human gates.

This repository is still the bootstrap memory for that product. The only
authoritative product inputs are:

- `docs/specs/engine-design-v3.md`
- `docs/mockups/foreman-mockup-v6.html`

Everything else in the repo exists to turn those two artifacts into a working
runtime without losing project memory along the way.

## Key references

- Agent operating instructions: `AGENTS.md`
- Project status: `docs/STATUS.md`
- Current sprint: `docs/sprints/current.md`
- Backlog: `docs/sprints/backlog.md`
- Architecture baseline: `docs/ARCHITECTURE.md`
- Roadmap: `docs/ROADMAP.md`

## Current state

The integrated pre-release baseline now contains:

- the product spec and UI mockup,
- two supervised autonomous entry points in `scripts/`,
- a runnable `foreman/` package with SQLite-backed models, store, and CLI,
- shipped declarative `roles/*.toml` and `workflows/*.toml` plus loader and
  prompt-rendering support,
- an orchestrator with built-ins for tests, merge, mark-done, human gates, and
  runtime context projection into `.foreman/`,
- repo-local `.foreman.db` discovery for normal CLI usage plus optional `--db`
  override semantics,
- `foreman init` defaulting to `<repo>/.foreman.db` for project scaffold
  generation and persisted project initialization,
- persisted human-gate approval and denial flows with deferred or immediate
  native resume depending on runtime availability,
- native Claude Code and Codex runners with structured event capture, retry
  normalization, explicit startup preflight checks, approval-policy handling,
  and persisted session reuse across fresh orchestrator invocations for
  persistent roles,
- an opt-in `development_secure` workflow that now runs end to end through
  code review, security review, test, and merge with durable carry-output
  semantics,
- store-backed monitoring commands for `board`, `history`, `cost`, and
  bounded `watch`,
- accepted ADRs for runner session and backend contract boundaries
  (`ADR-0001`) and dashboard data access (`ADR-0002`),
- a dashboard web surface with project overview, sprint board, task detail,
  activity feed, human message input, activity filtering, project switching,
  approve or deny actions wired into orchestrator resume, and a dedicated
  sprint event stream for live activity updates,
- unit and integration coverage across store, CLI, orchestrator, runners,
  dashboard, and runner-backed executor seams.

The current repo-memory goal is to keep that baseline coherent while moving
into the next implementation gap rather than leaving finished work stranded on
feature branches.

## Workflow selection

Use the default `development` workflow for standard bootstrap project setup.

Use `development_secure` when a project should require a dedicated security
review after code review and before tests and merge.

Example:

```bash
./venv/bin/foreman init /path/to/repo --name "Secure Project" --spec docs/spec.md --workflow development_secure
```

## Native backend preflight

Foreman now validates native backend prerequisites before long-running agent
execution starts.

- Claude Code requires a `claude` executable in `PATH`.
- Codex requires a `codex` executable in `PATH` plus a working app-server
  initialize and thread-start handshake.
- Preflight failures stop before `agent.started`, produce one explicit failed
  run, and do not consume infrastructure retries.

Operator recovery:

1. install or repair the missing backend executable,
2. verify the backend manually from the shell,
3. rerun the blocked task or project once the backend startup path is healthy.

## Autonomous entry points

Run all Python commands through the repo virtual environment:

```bash
./venv/bin/python scripts/reviewed_codex.py
./venv/bin/python scripts/reviewed_claude.py
```

What they do:

- `reviewed_codex.py` supervises a Codex development run against the current
  sprint docs and requests reviewer approval before accepting a completed
  slice.
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

The current sprint is `sprint-18-event-retention-pruning`.

The next recommended task is:

- implement spec-aligned pruning for old event rows while preserving events
  attached to blocked or in-progress tasks.

That work is recorded in `docs/sprints/current.md`, so a fresh agent can pick
it up without reconstructing branch history first.

## Validation

Current repo-memory validation:

```bash
./venv/bin/python scripts/validate_repo_memory.py
./venv/bin/python -m py_compile scripts/reviewed_codex.py
./venv/bin/python -m py_compile scripts/reviewed_claude.py
./venv/bin/python -m py_compile scripts/repo_validation.py
./venv/bin/python -m py_compile scripts/validate_repo_memory.py
```

Current code-level validation also includes:

```bash
./venv/bin/pip install -e . --no-build-isolation --no-deps
./venv/bin/python -m unittest discover -s tests -v
./venv/bin/foreman --help
./venv/bin/foreman projects
./venv/bin/foreman status
./venv/bin/foreman roles
./venv/bin/foreman workflows
./venv/bin/foreman approve --help
./venv/bin/foreman deny --help
./venv/bin/foreman board --help
./venv/bin/foreman history --help
./venv/bin/foreman cost --help
./venv/bin/foreman watch --help
./venv/bin/foreman dashboard --help
```
