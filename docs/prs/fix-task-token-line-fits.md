# fix/task-token-line-fits

## Summary

Under More details on a task, the token line wrapped its last word. It now
reads `170 in · 109.1K out · 14.9M cached` and fits.

## Tests

`npm --prefix frontend run lint`, `npm --prefix frontend test`; a screenshot
with `scripts/dashboard_shot.mjs`.
