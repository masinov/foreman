# Current Sprint

## Sprint 60 — what is there works and makes sense

- **Opened:** 2026-11-16 as "Foreman knows who did what" (identity, roles,
  audit). **Re-scoped the same day by the owner:** identity is not this
  project's concern now (the owner's company will build it separately and
  plug it in later). "You must focus on the actual app working properly and
  all the surfaces and features making sense and being functional."
- **Status:** in_progress
- **Method:** by hand unless a slice says otherwise. The engine is started
  only for the runs slices 1 and 9 name.

### Goal

Every screen and control of the dashboard does something a person can
follow, and every feature that is shown works end to end against a running
engine. Nothing new is added until that holds.

### Constraints

- Spec `docs/specs/engine-design-v3.md` for behaviour; ADR-0020 for the
  dashboard; ADR-0017 for what the API may set.
- No interface text that is a footnote about the implementation. A line of
  text is something the person acts on or needs to read a value (owner,
  2026-11-16).
- Read-only things look read-only and say once where they are changed.
- The owner is asked before a screen's structure changes; the audit of slice
  6 is brought as one review, not fixed piece by piece.

### Affected areas

`frontend/src/`, `foreman/dashboard/`, `foreman/services.py`,
`foreman/engine/`, `foreman/engine/orchestrator.py`, `foreman/roles/`, tests,
`docs/`.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 1 | One supervised run of the engine on a small task, to see sprint 59's fixes against a real agent | done | Foreman, watched by Claude | FOR-44 merged at `e59136a`; "The supervised run" below |
| 2 | Explain to the owner how roles, workflows, gates and model choice work | done | Claude | in conversation (the owner prefers plain explanations to pages); it found that a project could not have definitions of its own |
| 3 | A project's own roles and workflows, in the database, loaded over the shipped ones; tool names checked | done | Claude | `feat/project-definitions-in-database`: ADR-0024, migration 25, `foreman role`, `foreman workflow` |
| 4 | Roles and workflows editable from the dashboard | done | Claude | `feat/definitions-editor`: Roles tab and role form, step editor, text view; a prompt must say how its run ends; `none = true` for a role with no tool |
| 5 | What the architect was for. Decided with the owner: planning is the manager's, as two requests (plan a sprint, split a task), confirmed by a person or by Foreman under "Approve plans"; the architect role and its workflow go | done | Claude | `feat/planning-requests`: `foreman/manager/planning.py`, `add_task`, the two More-menu items; `refactor/remove-architect-role`: the role and workflow removed, migration 26 |
| 6 | Audit of every screen and control: does it work, can a person tell what it does, is anything shown that cannot be acted on; footnote strings listed | done | Claude | 28 screenshots of every page, tab, menu and dialog on a copy of the database; findings fixed in `fix/audit-what-is-shown` or brought to the owner as questions |
| 7 | The fixes from slice 6, in one batch | in_progress | Claude | `fix/audit-what-is-shown`: a merged task's changes and checks, who approved at a gate, no guidance or overrides on a finished task, explanation strings removed; the owner's answers to the open questions follow; `feat/workspace-definitions-editable`: the workspace's defaults are edited in Workspace settings, since a read-only list is not configuration (the owner) |
| 8 | The engine findings of slice 1: a sprint that closes itself, a branch behind `main` merged without being tested again, the developer using the system Python | done | Foreman, watched by Claude | Four tasks planned by the manager from "Plan this sprint" and run by the engine: ADR-0025 and spec 6.3 (the engine finishes a sprint only in an autonomous project; decided by Claude, the owner to confirm), the engine change, ADR-0026 (a branch behind is updated and tested again), the Python rule read from the repository's instructions |
| 9 | A second supervised run with several tasks | done | Foreman, watched by Claude | 2026-11-16, DB sprint `sprint-60b-engine-findings-of-the-supervised-run`: 4 tasks, 45 runs, $2.19, all merged and pushed by the engine. Seen against real agents: a plan made from the dashboard button and revised in the manager chat; a send-back at merge approval with a note the developer followed; a merge conflict between two tasks of the run sent back to develop and reconciled; two tasks in progress at once. Not seen: Run next, the new behind-branch path (the running engine was the old code) |
| 10 | The manager chat works for a person who is not on the machine (it is off on a network bind today) and FOR-43 if the owner accepts it | todo | Claude | |
| 11 | Close the sprint: checkpoint, archive | todo | Claude | `docs/checkpoints/`, `docs/sprints/archive/` |
| 12 | Fix the Foreman faults found by running Assay, the first outside project | done | Claude | 2026-11-18: `fix/checkout-follows-merges` (ADR-0031: a project folder on the default branch follows each merge); `fix/new-project-defaults` (merges wait for a person, workers on `claude-sonnet-5-5`); `fix/manager-faults-from-assay` (ADR-0022 amendment: a reply is seen while it is written, one message at a time; the manager's process ends with its turn; clearing declines waiting proposals; `ref` on `create_sprint` and `file_task`) |
| 13 | Block only before a task starts (owner, 2026-11-18) | done | Claude | `fix/block-only-before-start`, ADR-0030 amended |
| 14 | The backend in layers, held by a test (owner, 2026-11-19: "Architecture is not good. A refactor is needed.") | done | Claude | ADR-0032 and `.importlinter` (run in CI as `lint-imports`), in five branches that changed no behaviour: `refactor/layers-first-moves` (`domain/`, `repo/`, `definitions/`, the engine's root modules; `c82765e`), `refactor/layers-mutations` (`mutations/` by area, `history/`, no engine cycle; `167d8ac`), `refactor/layers-manager` (`manager/`; `e4551db`), `refactor/layers-services` (eleven services in place of `DashboardService`, `api/` in place of `dashboard/`; `3c238cc`), `refactor/layers-notifications` (`notifications/` by concern, imports at the top). Left, in ADR-0032: the CLI through the services, five long modules. The remaining sprint 60 items (the judge, "Finish sprints", reopening a sprint, Decline on the backlog) waited for it, as they touch the same files |

### The supervised run (slice 1, 2026-11-16)

FOR-44, "Say what the manager session can do in the off-loopback messages":
a wording fix in five files. The engine ran develop, test, review, the merge
gate, merge and push in eleven minutes for $0.23. Claude read the diff at
the gate and approved it. The engine was then shut down.

Seen working against a real agent:

- The push after a merge: `engine.push`, and `origin/main` was at the merge
  commit (`merge_push_remote=origin`, left on).
- The reviewer was started with Read, Grep and Glob only, and no agent had
  the operator's connectors (`--strict-mcp-config` on both runs).
- The approval was carried out three seconds after it was given, by the
  resident engine (it was idle, so this is not the case of slice 4 of
  sprint 59).
- Each run's cost is its session's own; no session was resumed.

Not exercised, so still covered by tests only: the cost of a resumed
session, the retry of a run that took no turn, Run next, a merge during
another task's step, the reviewer rule (the diff was small and whole).

Found:

- The sprint in the database closed itself when its only filed task was
  done, and a completed sprint cannot be made active again. The next tasks
  for this sprint need a new sprint entry. In `docs/sprints/backlog.md`.
- `main` moved while the task ran (a by-hand merge). The engine merged the
  branch without bringing it up to date, so the tests it recorded were for
  the branch head, not for what landed. CI covered the result.
- The developer used the system `python3` for an edit script, against
  `AGENTS.md`.

### Risks

- Slice 6 can grow without limit. It is an audit with a list, and the owner
  chooses what is fixed.
- Slices 8 and 9 touch when the engine merges and when a sprint ends.
- Slice 10 widens who can start an agent session on the host; it rests on the
  confinement of sprint 59 (ADR-0022 amendment).

### Validation

Before every merge: `ruff check foreman tests scripts`,
`./venv/bin/python -m unittest discover -s tests`,
`npm --prefix frontend run lint`, `npm --prefix frontend test`,
`npm --prefix frontend run build`,
`./venv/bin/python scripts/validate_repo_memory.py`. CI is read after every
push. Dashboard changes are looked at with `scripts/dashboard_shot.mjs`.
