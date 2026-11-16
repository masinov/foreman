# Current Sprint

## Sprint 60 — what is there works and makes sense

- **Opened:** 2026-11-16 as "Foreman knows who did what" (identity, roles,
  audit). **Re-scoped the same day by the owner:** identity is not this
  project's concern now (the owner's company will build it separately and
  plug it in later). "You must focus on the actual app working properly and
  all the surfaces and features making sense and being functional."
- **Status:** in_progress
- **Method:** by hand unless a slice says otherwise. The engine is started
  only for the runs slices 1 and 6 name.

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
  3 is brought as one review, not fixed piece by piece.

### Affected areas

`frontend/src/`, `foreman/dashboard/`, `foreman/dashboard_service.py`,
`foreman/engine/`, `foreman/orchestrator.py`, `foreman/roles/`, tests,
`docs/`.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 1 | One supervised run of the engine on a small task, to see sprint 59's fixes against a real agent | done | Foreman, watched by Claude | FOR-44 merged at `e59136a`; "The supervised run" below |
| 2 | A walkthrough for the owner: one task through a workflow, which role runs at each step, what it may do and must produce, where the gates are, how a model is chosen, what is set where | todo | Claude | a page for the owner |
| 3 | Audit of every screen and control: does it work, can a person tell what it does, is anything shown that cannot be acted on; footnote strings listed | todo | Claude | one review for the owner |
| 4 | The fixes the owner agrees from slice 3, in one batch | todo | Claude | |
| 5 | The engine findings of slice 1: a sprint that closes itself, a branch behind `main` merged without being tested again, the developer using the system Python | todo | Claude | fixes with tests |
| 6 | A second supervised run with several tasks, so that Run next, a merge during another step, a resumed session's cost and the reviewer rule are seen against a real agent | todo | Foreman, watched by Claude | what was seen, in this file |
| 7 | The manager chat works for a person who is not on the machine (it is off on a network bind today) and FOR-43 if the owner accepts it | todo | Claude | |
| 8 | Close the sprint: checkpoint, archive | todo | Claude | `docs/checkpoints/`, `docs/sprints/archive/` |

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

- Slice 3 can grow without limit. It is an audit with a list, and the owner
  chooses what is fixed.
- Slices 5 and 6 touch when the engine merges and when a sprint ends.
- Slice 7 widens who can start an agent session on the host; it rests on the
  confinement of sprint 59 (ADR-0022 amendment).

### Validation

Before every merge: `ruff check foreman tests scripts`,
`./venv/bin/python -m unittest discover -s tests`,
`npm --prefix frontend run lint`, `npm --prefix frontend test`,
`npm --prefix frontend run build`,
`./venv/bin/python scripts/validate_repo_memory.py`. CI is read after every
push. Dashboard changes are looked at with `scripts/dashboard_shot.mjs`.
