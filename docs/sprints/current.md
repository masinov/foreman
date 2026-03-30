# Current Sprint

- Sprint: `sprint-11-multi-project-dashboard-polish`
- Status: complete
- Goal: polish the dashboard for multi-project navigation, improve activity
  stream filtering, and add human message input capability
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`
  - `docs/adr/ADR-0002-dashboard-data-access-boundary.md`
  - `foreman/dashboard.py`

## Included tasks

1. `[done]` Add human message input to dashboard activity panel
   Deliverable: activity panel includes a text input and send button that POSTs
   to a new `/api/tasks/{id}/message` endpoint.

2. `[done]` Improve activity stream filtering
   Deliverable: activity filter dropdown allows filtering by event type or by
   task, matching the mockup's activity filter affordance.

3. `[done]` Add project switcher to dashboard topbar
   Deliverable: topbar shows current project with a dropdown to switch between
   projects when multiple exist.

## Excluded from this sprint

- authentication and multi-user concerns
- live streaming transport beyond polling
- task creation modal
- sprint creation modal

## Acceptance criteria

- a user can type a message in the activity panel and send it to a task
- activity stream can be filtered by event type
- dashboard supports navigation between multiple projects

## Known risks

- human message persistence requires new event type handling
- filtering may require additional store query methods
- project switcher state management adds JavaScript complexity
