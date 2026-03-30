# Sprint Archive: sprint-03-scaffold

- Sprint: `sprint-03-scaffold`
- Status: completed
- Goal: create a spec-driven `foreman init` path that scaffolds a target repo
  and persists the initialized project cleanly
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Final task statuses

1. `[done]` Implement repo scaffold generation for `foreman init`
   Deliverable: Foreman can create `AGENTS.md`, `docs/adr/`, `.foreman/`, and
   the necessary `.gitignore` updates in a target repository.

2. `[done]` Persist initialized projects and workflow settings from the CLI
   Deliverable: `foreman init` writes the project record into SQLite so later
   orchestrator runs can start from the generated scaffold instead of ad hoc
   seed scripts.

3. `[done]` Add integration coverage for scaffold generation and initialization
   Deliverable: tests prove the scaffold files, `.gitignore`, and persisted
   project state are created without touching tool-managed runtime paths.

## Deliverables

- `foreman.scaffold` rendering and idempotent scaffold generation for
  `AGENTS.md`, `docs/adr/`, `.foreman/`, and `.gitignore`
- `foreman init --db <path>` persisting new or existing project records with
  workflow, default-branch, and test-command settings
- store lookup by repo path so repeated initialization updates the same project
  instead of creating duplicates
- scaffold and CLI coverage for repo generation, persisted initialization, and
  preservation of a user-owned `AGENTS.md`

## Demo notes

- `./venv/bin/python -m unittest tests.test_scaffold tests.test_cli tests.test_store -v`
- `./venv/bin/foreman init <repo-path> --name "My Project" --spec <spec-path> --db <db-path>`

## Follow-ups moved forward

- `sprint-04-context-projection`: write `.foreman/context.md` and
  `.foreman/status.md` from SQLite before and after workflow activity
- backlog: human-gate resume commands, native runners, monitoring CLI, and
  dashboard implementation
