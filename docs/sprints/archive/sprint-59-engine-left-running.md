# Sprint 59 — the engine can be left running again (archived)

- **Opened:** 2026-11-15, the first sprint of Phase 5 of
  `docs/reviews/2026-11-10-full-review-and-finish-plan.md`. Scope agreed by
  the owner on 2026-11-15.
- **Status:** done (closed 2026-11-16)
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
| 5 | The engine pushes after a merge when the project asks for it | done | Claude | `feat/engine-push-after-merge`: host-level setting `merge_push_remote`, events `engine.push` and `engine.push_failed` |
| 6 | The reviewer must show what it read before it can approve | done | Claude | `feat/reviewer-must-read-before-approving`: role option `approve_needs_reading`, on for the four shipped reviewers |
| 7 | Agent sandbox, first cut: per-role tool allowlists passed to the runner, read-only reviewers, a scrubbed environment, no operator connectors | done | Claude | `feat/agent-sandbox-first-cut`: ADR-0023, `agent_env_passthrough`; checked with one real CLI call |
| 8 | The manager session is limited to its read surface (FOR-42) | done | Claude | `feat/manager-session-read-surface`: permission rules, drafts folder, ADR-0022 amendment; checked with a real manager turn on a database copy |
| 9 | A task's run output reads as sentences | done | Claude | `feat/task-run-output-in-sentences`: `runWords.js`, the API gives each event's facts, raw stream behind a disclosure |
| 10 | Editing a task's size, priority and dependencies after filing | done | Claude | `feat/task-edit-size-priority-dependencies`: `foreman task edit`, the Edit task dialog, loop check |
| 11 | Mark done and Reopen in the manager's proposals | done | Claude | `feat/manager-proposes-done-and-reopen`: `complete_task`, `reopen_task`, size and dependencies in `edit_task`; ADR-0022 amendment |
| 12 | Close the sprint: checkpoint, archive | done | Claude | `docs/checkpoints/2026-11-16-sprint-59-closed.md`, this file |

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

### What was checked against a real agent, and what was not

- Checked with the real Claude Code CLI (2.1.325, a few cents): a reading
  reviewer's tool set is exactly Read, Grep and Glob; the manager session is
  refused redirects, chained commands, `sqlite3`, `python`, `git commit` and
  reads outside the repository; one real manager turn on a copy of the
  database stored a proposal. That check found what the tests could not: an
  agent limited to three tools still had the operator's MCP connectors
  (closed with `--strict-mcp-config`).
- Tests only, no run of the engine: the cost fix (slice 2), the no-turn
  retry (1), Run next (3), a merge during another task's step (4), the push
  after a merge (5, against a local bare remote), the reviewer rule (6).
- The engine was not started during this sprint. The owner looked at the
  review page on 2026-11-16 and found nothing to correct.

### Left for later

- An agent process still runs as the engine's user with a shell and the
  network. A container per task is the rest of the plan's sandbox item.
- FOR-43 (the proposal card's "Then" row for a send-back, a summary line for
  earlier proposals) is not started. FOR-42's work is done (slice 8); both
  tasks still wait in the backlog of Foreman's own project for the owner to
  accept or decline.
- One mistake during the sprint: slice 9's doc edit removed a paragraph of
  `docs/ARCHITECTURE.md`; it was restored in `docs/restore-architecture-paragraph`.
