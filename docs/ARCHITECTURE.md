# Architecture

## Status

- Status: bootstrap implementation baseline
- Primary source: `docs/specs/engine-design-v3.md`
- UI reference: `docs/mockups/foreman-mockup-v6.html`
- ADRs: none accepted yet

This document describes the current architectural baseline for implementing
Foreman from the spec. It records active constraints without pretending that
unmade decisions are already settled.

## Product identity

Foreman is an autonomous development engine that:

- stores structured project state in SQLite,
- projects ephemeral context into a gitignored repo path,
- drives development through declarative roles and workflows,
- records runs and events for later inspection,
- exposes state to both CLI and UI surfaces.

It is not just a wrapper around one coding agent. The wrappers in `scripts/`
are bootstrap tooling, not the final product architecture.

## Core layers

The spec defines four layers:

1. Agent Runner
2. Role System
3. Workflow Engine
4. Orchestrator

Those layers should remain explicit in the codebase. Avoid collapsing them into
one monolithic service class or one prompt-heavy script.

## Source of truth

Foreman's runtime source of truth should be SQLite.

Primary entities:

- projects
- sprints
- tasks
- runs
- events

Committed markdown in this repository is temporary bootstrap memory for the
pre-implementation stage. Once the product exists, files like
`docs/STATUS.md` and `docs/sprints/current.md` should be treated as planning
artifacts or exports, not as the runtime database.

## Repo-level runtime boundary

The runtime repo integration should stay narrow:

- generated `AGENTS.md`
- `docs/adr/`
- gitignored `.foreman/`

Per the spec, convention docs such as branching and testing ultimately belong
in generated instructions rather than a sprawling committed scaffold. This repo
currently keeps them committed only because the product itself does not exist
yet.

## Recommended early package seams

The first package layout should closely follow the spec:

- `foreman/models.py`
- `foreman/store.py`
- `foreman/roles.py`
- `foreman/workflows.py`
- `foreman/orchestrator.py`
- `foreman/builtins.py`
- `foreman/scaffold.py`
- `foreman/context.py`
- `foreman/git.py`
- `foreman/cli.py`
- `foreman/runner/`

Support files outside the package:

- `roles/*.toml`
- `workflows/*.toml`
- `templates/*.j2`
- `tests/`

## Runner boundary

Foreman should support at least two runner backends:

- Claude Code
- Codex

Both need a shared protocol around:

- prompt input,
- session handling,
- structured events,
- time and cost gates,
- infrastructure error retries.

Do not let one backend's quirks leak into the shared orchestration model.

## Workflow boundary

Workflows should stay declarative and outcome-based.

Built-in steps from the spec that deserve explicit implementation seams:

- run tests
- merge
- mark done
- human gate
- context projection

The workflow layer should resolve transitions and loop limits from persisted
task state rather than by ad hoc control flow in runner scripts.

## Monitoring surfaces

Foreman needs two first-class observation surfaces:

- CLI inspection commands
- a web dashboard

The mockup establishes the main UI hierarchy:

- dashboard of projects
- project-level sprint views
- sprint-level task board with activity feed
- settings and creation modals

Implementation does not need to match the mockup pixel for pixel on day one,
but the object model and navigation hierarchy should match it.

## Bootstrap reality

Today the repo contains only:

- the spec,
- the mockup,
- bootstrap wrappers,
- repo-memory docs.

The first implementation slice has landed:

- `pyproject.toml` exists,
- the `foreman/` package scaffold exists,
- `foreman.cli` exposes the initial command shell,
- smoke tests cover `python -m foreman --help`, `projects`, and `status`.

The second implementation slice has now landed:

- `foreman.models` defines typed entities for projects, sprints, tasks, runs,
  and events,
- `foreman.store` bootstraps the SQLite schema and persists or queries the core
  entities,
- `foreman projects --db <path>` and `foreman status --db <path>` can inspect
  persisted state,
- round-trip tests cover the store baseline.

The third implementation slice has now landed:

- shipped default `roles/*.toml` and `workflows/*.toml` files mirror the spec's
  declarative examples,
- `foreman.roles` loads role definitions and renders prompt templates with the
  completion marker and signal docs,
- `foreman.workflows` loads workflow graphs and validates transitions against
  declared steps and known roles,
- `foreman roles` and `foreman workflows` expose the shipped definitions
  through the CLI.

The fourth implementation slice has now landed:

- `foreman.orchestrator` can select the next directed task from persisted
  sprint state and execute the loaded workflow graph step by step,
- `foreman.builtins` provides explicit seams for test, merge, mark-done, and
  human-gate pause behavior,
- `foreman.git` wraps the branch, merge, status, diff, and commit-history calls
  needed by workflow execution and reviewer prompts,
- `tests/test_orchestrator.py` drives the shipped development workflow against
  a real temporary git repo with a scripted executor.

The fifth implementation slice has now landed:

- `foreman.scaffold` generates the minimal repo scaffold described by the spec
  and renders `AGENTS.md` from `templates/agents_md.md.j2`,
- `foreman.cli` now supports `foreman init --db <path>` to initialize or
  update persisted projects directly from the command line,
- the store can look up projects by repo path so repeated initialization runs
  update the same project record instead of creating duplicates,
- `tests/test_scaffold.py` and the CLI smoke coverage verify scaffold
  generation, `.gitignore` behavior, and preservation of user-owned
  `AGENTS.md`.

Current runtime constraints worth preserving:

- every workflow step persists a `runs` row, including built-ins, so workflow
  and engine events always have a durable `run_id`,
- the orchestrator uses synthetic orchestrator runs for control-path events
  such as loop limits and crash recovery because the current schema requires
  `events.run_id` to be non-null,
- the shipped workflow TOML treats `_builtin:mark_done` as a terminal step with
  no outgoing edge, so the runtime currently treats `task.status == "done"` as
  successful workflow termination instead of a fallback block.
- `foreman init` never overwrites a repo's existing `AGENTS.md`; the generated
  instructions are a one-time scaffold that the user owns afterward,
- the bootstrap CLI currently requires explicit `--db PATH` selection for
  project lifecycle commands until engine-level database discovery exists.

The next implementation slice should project `.foreman/context.md` and
`.foreman/status.md` from SQLite before and after workflow activity so agents
receive fresh runtime context from the engine instead of bootstrap docs.
