# Current Sprint

## Sprint 60 — Foreman knows who did what

- **Opened:** 2026-11-16, the second sprint of Phase 5 of
  `docs/reviews/2026-11-10-full-review-and-finish-plan.md`. Scope agreed by
  the owner on 2026-11-16.
- **Status:** in_progress
- **Method:** decided per slice. The owner allowed the engine to be started
  for one supervised run (2026-11-16); slice 1 is that run. What it shows
  decides whether later slices are given to the engine or done by hand.

### Goal

Today every decision is recorded as made by whoever holds the one dashboard
token. After this sprint a person signs in, has a role, and every decision
names the actor the server derived. No identity provider is chosen (owner,
2026-11-10): the sprint delivers the seam and one built-in way to fill it.

### Constraints

- Spec `docs/specs/engine-design-v3.md` for behaviour; ADR-0016 (browser
  routes into the API), ADR-0017 (what the API may set), ADR-0022 (the
  manager proposes), ADR-0023 (what an agent is handed).
- The identity decision gets its own ADR before code depends on it (slice 2).
- The shared token keeps working for a single-operator install; nothing that
  runs today stops running.
- Dashboard changes follow ADR-0020 and the look rules in `docs/TESTING.md`.

### Affected areas

`foreman/dashboard/`, `foreman/dashboard_guard.py`, `foreman/store/`,
`foreman/mutations.py`, `foreman/meta_agent.py`, `foreman/runner/`,
`foreman/cli/`, `frontend/src/`, tests, `docs/`.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 1 | One supervised run of the engine on a small task, to see sprint 59's fixes against a real agent | done | Foreman, watched by Claude | FOR-44 merged at `e59136a`; "The supervised run" below |
| 2 | An ADR for identity: users, the four roles (viewer, operator, approver, admin), where a provider plugs in | todo | | `docs/adr/` |
| 3 | Users and sessions in the database; sign in with a built-in local provider behind the seam | todo | | migration, CLI to add a user, sign-in page |
| 4 | Every decision (approve, send back, mark done, confirm a proposal, settings) records the actor the server derived, never one the client sent | todo | | |
| 5 | Roles enforced on the API and shown in the dashboard: a viewer cannot approve, only an admin changes host-level settings | todo | | |
| 6 | Audit events cannot be changed or deleted | todo | | |
| 7 | Manager chat through the runner: a declared tool set, a session per user, one turn at a time, stopped when the person leaves, cost per turn | todo | | |
| 8 | FOR-43, if the owner accepts it: the proposal card's "Then" row for a send-back, a summary line for earlier proposals | todo | | |
| 9 | Close the sprint: checkpoint, archive | todo | Claude | `docs/checkpoints/`, `docs/sprints/archive/` |

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

- Slice 1 runs an agent as the engine's user with a shell and the network.
  It is one small task, watched, with the merge behind a human gate.
- Slices 3 to 5 sit in front of every request. A mistake locks the operator
  out or lets a viewer act; the token path stays as the way back in.
- Slice 7 replaces how the manager is started. Its confinement from sprint
  59 (ADR-0022 amendment) must hold through the runner.

### Validation

Before every merge: `ruff check foreman tests scripts`,
`./venv/bin/python -m unittest discover -s tests`,
`npm --prefix frontend run lint`, `npm --prefix frontend test`,
`npm --prefix frontend run build`,
`./venv/bin/python scripts/validate_repo_memory.py`. CI is read after every
push. Dashboard changes are looked at with `scripts/dashboard_shot.mjs`.
