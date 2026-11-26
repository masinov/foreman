# Branches and the operator checkout

Moved from `docs/STATUS.md` on 2026-11-26.

- `main` is pushed to `origin/main`. Work happens on short branches from
  `main`; the operator checkout stays off `main` (the `_integration`
  worktree holds it).
- The built dashboard bundle is not in git; `foreman dashboard` builds it
  when it is missing or stale.
- A sprint's copies (`docs/STATUS.md`, `docs/sprints/current.md`, its archive
  file) and `CHANGELOG.md` are written by Foreman on `main`, in the
  `_integration` worktree, when a sprint starts or finishes (ADR-0040).
