# PR Summary: chore/phase0-baseline

## Summary

- Phase 0 of the 2026-11-10 finish plan: one clean, CI-checked baseline on
  top of `main` before any safety work starts.
- Merges the three unmerged operator UI fixes (Manager folded by default,
  regrouped project header, working-copy controls in Settings) with `main`'s
  policy matrix and triage UI, including edits that were still uncommitted
  in the operator checkout.

## Scope

- Merge and bundle rebuild; no behaviour change beyond what the merged
  branches already carried.
- CI workflow, ruff baseline (syntax and pyflakes rules), `dev` extra.
- Repo memory: compact `docs/STATUS.md`, sprint 54 archived, sprint 55
  opened, backlog re-ordered, the 2026-09-08 and 2026-11-10 reviews added.

## Files changed

- `frontend/src/*`, `foreman/dashboard_frontend_dist/*` (merge, rebuilt)
- `.github/workflows/ci.yml`, `pyproject.toml`, `.gitignore`
- `foreman/cli.py`, `foreman/dashboard_runtime.py`, `foreman/meta_agent.py`,
  `foreman/orchestrator.py` (unused imports, a dead duplicate method)
- `tests/test_orchestrator.py` and five other test modules (lint; one lost
  class header restored)
- `docs/STATUS.md`, `docs/sprints/*`, `docs/reviews/*`, `docs/prs/*`,
  `docs/checkpoints/status-history-through-2026-09-08.md`, `CHANGELOG.md`,
  `docs/TESTING.md`

## Migrations

- none

## Risks

- The CI workflow has not run on GitHub yet; the first push will show
  whether the suite passes outside this machine (it shells out to git and
  builds worktrees).
- The bundle-freshness check assumes the Vite build is reproducible across
  Node 22 on CI and Node 24 locally. If hashes differ, pin the Node version.
- `docs/STATUS.md` was rewritten from 1,067 lines to a snapshot; the old
  text is preserved verbatim in `docs/checkpoints/`.

## Tests

- `python -m unittest discover -s tests`: 989 pass, 1 skipped (983 before;
  six evidence tests had been shadowed by a lost class header and now run)
- `npm --prefix frontend test`: 50 pass
- `npm --prefix frontend run build`: clean
- `ruff check foreman tests scripts`: clean
- `scripts/validate_repo_memory.py`: pass

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- One branch carries every piece of pending work; nothing lives only in an
  uncommitted checkout.
- Tests, lint and build run from one CI definition.
- A fresh agent can read `docs/STATUS.md` in under a minute and find the
  current sprint and plan.

## Follow-ups

- Owner: confirm merge to `main` and push; confirm the `.foreman.db`
  reconciliation listed in `docs/STATUS.md`.
- Sprint 55 slices 1 to 6 (host and money safety).
- ESLint and style rules arrive with the Phase 3 and 4 splits.
