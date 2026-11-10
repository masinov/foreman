# STATUS

Current snapshot only. History up to 2026-09-08 (sprints 1 to 54) is in
`docs/checkpoints/status-history-through-2026-09-08.md`.

## Where the project is (2026-11-10)

- Driving document: `docs/reviews/2026-11-10-full-review-and-finish-plan.md`
  (full review of engine, runner, dashboard, frontend and UX, with a six-phase
  plan, 0 to 5).
- Active sprint: **sprint 55 — baseline and host safety**
  (`docs/sprints/current.md`). Sprint 54 is closed and archived.
- `main` carries sprint 55 slices 0 to 2 and is pushed to `origin/main`.
  Work happens on short branches from `main`; the operator checkout stays
  off `main` (the `_integration` worktree holds it).

## Do not run unattended yet

Until sprint 55 slices 3 to 6 land, do not run `foreman serve` unattended.
Still open from the review: a cost gate that cannot stop spend mid-run,
agents that can outlive the engine, a lease loss that re-runs the developer
agent without bound, and approve/deny running workflow steps outside the
engine lock. Closed so far: the browser routes into the API (ADR-0016) and
API control over shell commands, storage paths and role permissions, plus
prune deleting non-worktree directories (ADR-0017).

## Operating decisions (owner, 2026-11-10)

- Claude drives the work. Whether a slice runs by hand or through Foreman is
  decided per slice; cost and safety observations from Foreman runs are
  recorded in the sprint doc.
- No identity provider or notification channel is being chosen now. Login and
  notification stay pluggable seams for adopters to fill.
- Codex stays in the tree but is treated as experimental until it has a
  shipped role, cost accounting and a real-binary smoke test.

## Documented conflicts between spec, mockup and code

- Shipped workflows test before review and gate the merge behind a
  policy-governed human gate; spec §5 shows review first.
- `_builtin:mark_done` terminates a workflow with no outbound transition.
- Events require a run and a task, so project-level events attach to a
  synthetic system run on one project task.
- Spec §6.2 says a missing `signal.task_started` degrades; the code blocks
  the task. Spec §6.4 sprint checkpoints (tag, note, event) are not built.
- ADR-0007 describes a restricted planner session; the shipped manager chat
  is a full-access Claude Code session.
- ADR-0011 says one engine per project; `foreman approve`/`deny` and the
  dashboard's Approve still run workflow steps outside the engine lock.
- The dashboard has diverged from `docs/mockups/foreman-mockup-v6.html`
  (project view, settings, policy matrix, triage, manager chat). The mockup
  is no longer an accurate reference for those screens; a design reference
  for the frontend rebuild is planned in Phase 4.

## Validation baseline

- `./venv/bin/python -m unittest discover -s tests` (989 tests)
- `npm --prefix frontend test` (50 tests) and `npm --prefix frontend run build`
- `ruff check foreman tests scripts` (pyflakes and syntax rules)
- `./venv/bin/python scripts/validate_repo_memory.py`
- CI runs all of the above plus a check that the committed bundle matches
  the source (`.github/workflows/ci.yml`).
