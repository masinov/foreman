# Current Sprint

## Sprint 59 — the engine can be left running again

- **Opened:** 2026-11-15, the first sprint of Phase 5 of
  `docs/reviews/2026-11-10-full-review-and-finish-plan.md`. Scope agreed by
  the owner on 2026-11-15.
- **Status:** in_progress
- **Method:** by hand, on short branches. The engine stays stopped (owner,
  2026-11-13) until this sprint's fixes are in; whether to start it again is
  the owner's call at the end.

### Goal

Sprint 58 ended with the engine stopped and a list of defects found while it
ran. This sprint fixes them and narrows what an agent can do on the host, so
that running the engine unattended is a reasonable thing to do again.

### Constraints

- Spec `docs/specs/engine-design-v3.md` for behaviour; ADR-0011 (gates),
  ADR-0012 (worktrees), ADR-0017 (what the API may set), ADR-0018 (evidence
  is facts), ADR-0022 (the manager proposes).
- Each engine fix comes with a test that fails without it. No fix is called
  proven against a real agent unless it was run against one.
- Roles and workflows stay declarative TOML; nothing is hard-coded per
  project.
- Dashboard changes follow ADR-0020 and the look rules in `docs/TESTING.md`.

### Affected areas

`foreman/engine/`, `foreman/orchestrator.py`, `foreman/serve.py`,
`foreman/runner/`, `foreman/roles/`, `foreman/mutations.py`,
`foreman/dashboard_service.py`, `frontend/src/pages/task/`, tests, `docs/`.

### Slices

| # | Slice | Status | Executed by | Deliverable |
|---|-------|--------|-------------|-------------|
| 1 | A corrective retry that ends with zero turns is not a second failure | done | Claude | `fix/engine-retry-that-ran-no-turn`: `NoTurnError`, the same prompt is sent again; the correction no longer asks for the marker when the work is unfinished |
| 2 | A resumed session's cost is counted once, not on every run | done | Claude | `fix/engine-session-cost-counted-once`: migration 24, `runs.session_cost_usd` |
| 3 | `foreman engine run-task` takes effect without a restart | done | Claude | `fix/engine-run-request-jumps-the-queue`: a pass ends between tasks when a request or command is waiting |
| 4 | An approved merge does not wait behind another task's step | done | Claude | `fix/engine-approved-merge-does-not-wait`: the running step carries out other tasks' approved merges; ADR-0011 amendment |
| 5 | The engine pushes after a merge when the project asks for it | todo | Claude | setting, fix, test |
| 6 | The reviewer must show what it read before it can approve | todo | Claude | role contract, test |
| 7 | Agent sandbox, first cut: per-role tool allowlists passed to the runner, read-only reviewers, a scrubbed environment | todo | Claude | runner, roles, ADR |
| 8 | The manager session is limited to its read surface (FOR-42) | todo | Claude | runner, test |
| 9 | A task's run output reads as sentences | todo | Claude | `pages/task/` |
| 10 | Editing a task's size, priority and dependencies after filing | todo | Claude | API, CLI, dialog |
| 11 | Mark done and Reopen in the manager's proposals | todo | Claude | ADR-0022 amendment, proposal kinds |
| 12 | Close the sprint: checkpoint, archive | todo | Claude | `docs/checkpoints/`, `docs/sprints/archive/` |

### Risks

- Slices 3 and 4 change when the engine acts. They are the ones most likely
  to disturb the step loop; each keeps the lease and lock rules of ADR-0011.
- Slice 5 makes the engine write to a remote. It is off unless the project
  turns it on, and a failed push never undoes a merge.
- Slices 7 and 8 can make a role unable to do its job. Each role's allowlist
  is checked against what its prompt asks it to do.
- Nothing here can be seen against a real agent without starting the engine.
  What is only covered by tests is said so in the checkpoint.

### Validation

Before every merge: `ruff check foreman tests scripts`,
`./venv/bin/python -m unittest discover -s tests`,
`npm --prefix frontend run lint`, `npm --prefix frontend test`,
`npm --prefix frontend run build`,
`./venv/bin/python scripts/validate_repo_memory.py`. CI is read after every
push. Dashboard changes are looked at with `scripts/dashboard_shot.mjs`.
