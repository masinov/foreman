# Backlog

## Next up after current sprint

Remaining items from the sprint-30 gap analysis:

- **Sprint creation modal inline task entry** — mockup allows adding tasks during
  sprint creation; currently the modal only captures title and goal
- **Task cancellation UI** — no button or action to cancel a task from the board
  or task detail drawer; backend supports `cancelled` status via `save_task`
- **Task dependencies display** — `depends_on_task_ids` exists in the model but
  is not shown in the task detail drawer
- **Event log load-more** — `list_sprint_events` supports `after_event_id` but
  the frontend never paginates past the initial 50 events
- **Sprint status filter for `cancelled`** — sprint list filter only shows
  All/Active/Done/Planned; cancelled sprints have no dedicated filter path

## Parking lot

- optional PR summary and checkpoint automation
- Codex cost capture if the app-server contract begins returning USD pricing
