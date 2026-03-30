# AGENTS.md

## Purpose

This repository builds **Foreman**, an autonomous development engine for
spec-driven software delivery.

Foreman is defined first by two repository artifacts:

1. `docs/specs/engine-design-v3.md`
2. `docs/mockups/foreman-mockup-v6.html`

Everything else in this repo exists to help agents turn those two files into a
working product without losing project memory along the way.

Treat the repository as durable project memory. Do not rely on chat history as
the source of truth.

## Read Before Writing

Before making non-trivial changes, read these in order:

1. `docs/specs/engine-design-v3.md`
2. `docs/mockups/foreman-mockup-v6.html`
3. `docs/STATUS.md`
4. `docs/sprints/current.md`
5. `docs/sprints/backlog.md`
6. relevant ADRs in `docs/adr/`
7. relevant implementation files and tests

If the spec, mockup, and current code disagree:

1. trust the spec for system behavior,
2. trust the mockup for UI information architecture and interaction intent,
3. document the conflict in `docs/STATUS.md` before changing behavior.

The mockup is a product-behavior and UI-structure reference. It does not, by
itself, define the implementation stack. Implementation-stack decisions belong
in ADRs and architecture docs, and once made they must be followed explicitly.

Do not casually edit the spec or mockup. Only change them when the task
explicitly revises product direction.

## Environment

- Always use the repository virtual environment at `./venv`.
- Never use system `python`, `python3`, or `pip`.
- Run Python tools with `./venv/bin/python` and `./venv/bin/pip`.

## Current Project Reality

This repository is at a bootstrap stage for **project memory and feature
coverage**, not for implementation quality. The spec and mockup are
authoritative; the implementation is still being built.

Until Foreman itself exists, this repo uses committed markdown files as a
temporary project-memory scaffold:

- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`

Do not confuse this bootstrap scaffold with permission to land throwaway or
prototype-grade architecture. Per the spec, Foreman's runtime source of truth
should move into SQLite, with markdown becoming projection rather than primary
state.

## Implementation Standard

Every landed slice must move the codebase toward a robust production product,
even when the feature set is incomplete.

Rules:

- bootstrap status refers to repo memory and sequencing, not to code quality,
- do not land implementation shapes that are obviously meant to be thrown away,
- do not justify weak boundaries by saying the product is "not finished yet",
- if a slice would require a knowingly bad architecture shortcut, stop and
  record a reset or refactor slice instead of normalizing the shortcut,
- product surfaces may be partial, but the parts that land should be able to
  survive into the final product with incremental refinement rather than full
  replacement.

## Planning Rules

Do not jump into non-trivial coding without first stating:

- goal,
- constraints,
- affected areas,
- implementation plan,
- risks,
- validation steps.

Prefer small vertical slices over broad rewrites. A good slice usually lands a
visible capability end to end: schema, store, CLI or API seam, tests, and
docs.

Small vertical slices still need durable seams. "Small" is not a reason to
inline a future subsystem into the wrong module or skip the architectural
boundary the product will need anyway.

If the current sprint is exhausted, pull the next justified slice from
`docs/sprints/backlog.md` and update sprint state as part of the same change.

## Product Guardrails

Preserve the core architecture from the spec:

- Agent Runner
- Role System
- Workflow Engine
- Orchestrator

Preserve the core product commitments:

- SQLite is the structured source of truth for projects, sprints, tasks, runs,
  and events.
- `.foreman/` is runtime context projection, not committed product state.
- roles and workflows are declarative TOML, not hard-coded per project.
- both Claude Code and Codex backends remain first-class targets.
- the dashboard and sprint/task views should stay aligned to the mockup's
  hierarchy and affordances.
- product web UI should live in dedicated frontend code, not as embedded HTML
  strings inside backend modules.
- backend modules should expose durable API, orchestration, and persistence
  boundaries rather than mixing transport, rendering, and storage concerns.
- completed product-facing commands should not remain stubs or placeholder
  surfaces unless the current sprint is explicitly about scaffolding that
  command and the unfinished state is documented as a known gap.

Avoid carrying old Apparatus-specific concepts into this codebase. This repo is
not a research-writing product, and no leftover domain language from that
project should survive in docs, code, prompts, validation, or examples.

## Tool-Managed State

Do not manually edit tool-managed runtime state unless the task is explicitly
about those files:

- `.foreman/`
- `.codex/`
- `.claude/`

These paths should stay gitignored.

## Branching

Use short-lived branches for all non-trivial work.

Branch naming:

- `feat/<scope>-<short-description>`
- `fix/<scope>-<short-description>`
- `refactor/<scope>-<short-description>`
- `docs/<scope>-<short-description>`
- `spike/<scope>-<short-description>`
- `chore/<scope>-<short-description>`

Rules:

- Never work directly on `main`.
- One branch should represent one coherent task or slice.
- If work expands, split it rather than letting the branch sprawl.
- If a branch is paused, leave a status note in `docs/STATUS.md` or
  `docs/prs/<branch-name>.md`.

## Commits

Use small, coherent commits with conventional prefixes:

- `feat:`
- `fix:`
- `refactor:`
- `test:`
- `docs:`
- `chore:`

Do not mix unrelated refactors with feature work unless necessary to unblock
the slice.

## Sprint Execution

All non-trivial work should be tied to a sprint or backlog item.

Canonical files:

- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/`

Task statuses:

- `todo`
- `in_progress`
- `blocked`
- `done`

Each completed task should leave behind a visible deliverable such as:

- a working CLI command,
- a passing test suite addition,
- a store or schema slice,
- a runner integration,
- a UI screen,
- an ADR,
- a documented experiment result.

“Worked on X” is not a deliverable.

A deliverable is not complete if it only works through a knowingly weak
implementation boundary that the next sprint must discard.

## Documentation Expectations

Keep these docs current when relevant:

- `README.md`
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/BRANCHING.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `CHANGELOG.md`

Create ADRs in `docs/adr/ADR-XXXX-title.md` when a decision becomes an active
implementation constraint. Good ADR candidates in this repo include:

- SQLite schema shape,
- orchestrator loop semantics,
- runner session handling,
- human-gate behavior,
- merge policy,
- API or UI boundary,
- security review path,
- cost and time gate policy.

When a UI or API boundary decision is made, future slices must follow it. Do
not continue landing code that violates an accepted ADR just because the
violating implementation already exists.

Do not front-load speculative ADRs. Put open questions in `docs/STATUS.md` or
`docs/ROADMAP.md` until the code actually depends on a decision.

Every meaningful branch should update at least one repo doc.

## PR Summaries And Checkpoints

Every branch should produce a PR-style summary at:

- `docs/prs/<branch-name>.md`

Use the repository template and include:

- summary,
- scope,
- files changed,
- migrations,
- risks,
- tests,
- output examples or screenshots when relevant,
- acceptance criteria satisfied,
- follow-ups.

Create checkpoint notes at meaningful milestones in:

- `docs/checkpoints/<tag>.md`

## Validation

Before marking work complete, run the relevant validation for the slice.

Current baseline validation for repo-scaffold work:

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`

As implementation lands, add and run:

- unit tests for models, store, and loaders,
- integration tests for orchestrator and built-ins,
- runner smoke tests,
- manual UI validation notes against the mockup.

Work is not done if it only compiles.
Work is also not done if it lands a user-facing surface through an
architecture that is already known to be unacceptable for the product.

## Wrapper Expectations

The repo currently exposes two supervisor entry points:

- `scripts/reviewed_codex.py`
- `scripts/reviewed_claude.py`

They read this file plus sprint and status docs to decide what the next slice
is. Keep those docs concrete enough that a fresh agent can start without human
re-explanation.

If a supervisor prompt requires a structured completion marker, follow that
prompt exactly.

## Required Task Output

When finishing a task, always provide:

1. What was completed
2. Deliverables
3. Files changed
4. Tests run
5. Open risks
6. Suggested next task
7. Documentation updated
8. Branch name used

If blocked, provide:

- blocking issue,
- current branch state,
- recommended next move,
- whether to continue from current state or revert.
