# Current Sprint

- Sprint: `sprint-08-monitoring-cli`
- Status: active
- Goal: expose active Foreman state through CLI board, history, watch, and
  cost surfaces without opening SQLite manually
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/mockups/foreman-mockup-v6.html`

## Included tasks

1. `[todo]` Add `foreman board --db <path>` for current sprint task inspection
   Deliverable: operators can list active sprint tasks grouped by status with
   task type, branch, assigned role, and blocked reason context.

2. `[todo]` Add `foreman history --db <path>` and `foreman cost --db <path>`
   for run and event inspection
   Deliverable: operators can inspect recent task history plus persisted cost
   or token summaries from SQLite without manual queries.

3. `[todo]` Add `foreman watch --db <path>` as a polling activity snapshot
   Deliverable: the CLI can refresh task counts and recent activity in a
   mockup-aligned monitoring view suitable for terminal use.

## Excluded from this sprint

- ADR authoring beyond noting the now-active runner questions
- dashboard and web implementation
- schema migration framework work

## Acceptance criteria

- `foreman board` exposes the active sprint task board directly from SQLite
- `foreman history` and `foreman cost` expose recent runs, events, and usage
  summaries without opening the database manually
- `foreman watch` provides a useful polling view of active project activity
- docs and validation remain good enough for a fresh autonomous agent to pick
  the next slice without extra human context

## Known risks

- the monitoring commands must stay aligned to the mockup hierarchy without
  prematurely committing to a full web API boundary
- Codex runs currently lack USD telemetry, so cost surfaces may need to expose
  token summaries and explicit placeholders rather than inferred pricing

## Demo checklist

- show one project board view from SQLite
- show one history or cost query returning persisted run data
- show the polling watch view refreshing without corrupting state
- show repo validation passing after the monitoring CLI slice lands
