# fix/decision-on-one-line-when-it-fits

## Summary

The decision banner on the task page always put the question on one line and
its facts on the next. For "Accept this task?" that is two lines for two
short facts.

## Scope

`frontend/src/styles/task.css`: the banner's body wraps instead of stacking.

## Files changed

One stylesheet, changelog.

## Migrations

None.

## Risks

None known.

## Tests

`npm --prefix frontend test`. CSS only. Seen in a screenshot.

## Follow-ups

None.
