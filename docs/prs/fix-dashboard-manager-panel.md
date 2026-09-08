# PR Summary: fix/dashboard-manager-panel

## Summary

The sprint overview opened Manager on arrival and called its folded tab
"Agent", conflating planning/supervision with execution activity. Manager now
starts folded, opens through a Manager tab, and preserves its mounted chat and
draft when folded again. Each project gets its own panel state.

## Scope

Sprint 54 operator UI correction in the existing React frontend. Manager
state and layout selectors have distinct names; sprint execution controls and
the Agent activity filter keep their existing behavior.

## Files changed

- `frontend/src/components.jsx`: folded default, lazy mount, Manager naming
  and accessible panel/open/collapse controls.
- `frontend/src/styles.css`: Manager-specific layout selectors.
- `frontend/src/App.jsx`: project-keyed sprint overview state.
- `frontend/src/App.test.jsx`: regression for initial folding, naming,
  retained draft and navigation to sprint execution activity.
- `foreman/dashboard_frontend_dist/`: rebuilt shipped frontend.
- `docs/STATUS.md`, `docs/sprints/current.md`, this summary.

## Migrations

None.

## Risks

Manager's existing network access policy still applies. This UI change does
not enable remote Manager execution. Unsaved drafts survive folding within
the current project view; navigation away still unmounts the view.

## Tests

- `cd frontend && npm test`: 39 tests passed.
- `cd frontend && npm run build`: passed.
- Live Chromium check at 1440 × 1000: folded default, correct tab, retained
  draft on folding/reopening, folded state after reload, and separate sprint
  activity all passed with no page errors. Screenshots inspected.
- Repository memory validation, validator compilation and `git diff --check`:
  passed.
- No backend code changed; backend unit tests were not rerun.

## Screenshots or output examples

The folded sprint overview has a `Manager` edge tab; opening it shows
`Manager` and `Planning & supervision`. The sprint execution view retains
its separate `Activity` panel and `Agent` event filter.

Local captures: `/tmp/foreman-manager-folded.png` and
`/tmp/foreman-manager-open.png`. The dashboard at `http://odin:8212/dashboard`
was restarted via this checkout's `./venv/bin/python -m foreman`; the served
HTML was checked against the rebuilt assets. Access token unchanged.

## Acceptance criteria satisfied

- Manager starts folded and does not load chat history until opened.
- Sprint overview identifies its planning panel as Manager.
- Folding/reopening retains the draft and does not reload history.
- Sprint execution activity remains separate.

## Follow-ups

Review the retained UX findings before proposing the next focused change.
