# Backlog

## Next up after current sprint

- `sprint-14-dashboard-streaming-transport` — replace polling-only dashboard
  activity with an explicit live transport boundary that stays aligned with
  the spec and current `foreman watch` semantics
- `sprint-15-security-review-workflow` — add a declarative security review
  workflow variant with orchestrator and CLI coverage

## Parking lot

- event-retention pruning
- optional PR summary and checkpoint automation
- engine-level database discovery so SQLite-backed commands do not require
  explicit `--db`
- native backend preflight health checks for `claude` and `codex`
- Codex cost capture if the app-server contract begins returning USD pricing
