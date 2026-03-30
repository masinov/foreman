# Sprint Archive: sprint-11-multi-project-dashboard-polish

- Sprint: `sprint-11-multi-project-dashboard-polish`
- Status: completed
- Goal: polish the dashboard for multi-project navigation, improve activity
  stream filtering, and add human message input capability
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
  - `foreman/dashboard.py`

## Final task statuses

1. `[done]` Add human message input to dashboard activity panel
   Deliverable: the activity panel can POST a message to the selected task and
   persist it as a `human.message` event.

2. `[done]` Improve activity stream filtering
   Deliverable: the activity panel can filter visible events by category
   without leaving the current sprint board.

3. `[done]` Add project switcher to dashboard topbar
   Deliverable: the dashboard can switch between projects from the topbar when
   multiple projects exist.

## Deliverables

- dashboard activity input wired to `POST /api/tasks/{id}/messages`
- persisted `human.message` events for operator feedback in the activity feed
- activity filter UI for all, commands, files, signals, and human messages
- project switcher UI for multi-project navigation
- expanded dashboard coverage for message input, filtering, and project
  switcher affordances
- repo-memory rollover from dashboard polish to dashboard approve or deny
  integration

## Demo notes

- `./venv/bin/python -m unittest tests.test_dashboard -v`
- `./venv/bin/python -m unittest discover -s tests -v`

## Follow-ups moved forward

- `sprint-12-dashboard-approve-deny-integration`: make blocked-task approve
  and deny actions resume the workflow
- backlog: dashboard streaming transport, security review workflow variant,
  event-retention pruning, and optional PR or checkpoint automation
