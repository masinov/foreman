# docs/sprint-58-state-and-look-check

## Summary

Repo memory caught up with sprint 58, and the tool that lets an agent see a
page is in the repository.

## Scope

- `scripts/dashboard_shot.mjs`: headless Chrome over its debugging protocol,
  Node only. Captures after `click:`, `hover:`, `type:` and `wait:` steps.
- `docs/TESTING.md`, "Checking the look": how to use it and the fifteen
  rules taken from the owner's review of 2026-11-13.
- `docs/sprints/current.md`: every slice's real status and who did it; what
  Foreman did well and badly on this sprint.
- `docs/sprints/backlog.md`: engine defects found, dashboard follow-ups.
- `docs/STATUS.md`: where the project is, design deviations, baseline.
- ADR-0020 amendments and the design README: the backlog is a page.
- `docs/ARCHITECTURE.md`: sign-in gate, live data.
- `docs/prs/chore-operator-checkout.md`: the operator checkout's branch.

## Migrations

None. No product code changes.

## Tests

`./venv/bin/python scripts/validate_repo_memory.py`; the script was used to
capture the dialogs and menus of the four preceding branches.

## Follow-ups

ESLint; close the sprint.
