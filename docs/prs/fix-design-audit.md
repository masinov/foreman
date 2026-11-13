# fix/design-audit

## Summary

One pass over every dashboard page against the rules the owner's corrections
imply (a title sits on a rule; a count is a figure beside its label; gold
means "needs a person"; one way to say one thing; nothing wraps that fits).
Found from screenshots of all fifteen pages, fixed in one batch.

## Scope

Frontend only. No API, schema or engine change.

## What changed

- Needs you says what was checked in the sprint list's words and colours
  (`tests · review · sha`) and no longer wraps; at phone width a row is a
  small block instead of a squeezed table.
- "n need you" is gold wherever task counts appear (workspace, sprint queue,
  sprint summary); counts name cancelled tasks so they add up to the rows.
- A heading's count is gold only when it counts what waits for a person.
- Numeric column headers sit over their figures (`numeric` on a `Table`
  column).
- Project: the engine label is quiet; the Sprints tab has a ruled heading
  ("Active and planned") with New sprint as its action; the Activity tab's
  filter is on the heading row and the heading no longer repeats the tab.
- Backlog and project settings pages show the engine in the top bar and the
  same project crumb as every other page.
- Sprint: summary labels sit beside their values; Tasks is a ruled heading
  with the List/Board choice and the actions on it; board columns with cards
  are wide enough to read, empty ones narrow, keys and checks never wrap.
- Task: Checks summary links from its heading; the two Checks tables share
  columns; a criterion drops its list dash and the repeated "not checked"
  line.
- Settings: label column narrowed; drop-downs match the other inputs;
  the workflow's source line is under its heading, not in it.
- Top bar at phone width: two rows, controls as icons, nothing wraps.

## Migrations

None.

## Risks

Look only. Hover and motion cannot be seen in a still screenshot.

## Tests

`npm --prefix frontend test` (336 pass), `./venv/bin/python -m unittest
discover -s tests` (1329 pass, 1 skipped), `npm --prefix frontend run build`.

## Follow-ups

The capabilities in `docs/design/dashboard-v7/legacy-capabilities.md` that
have no home yet; live updates; ESLint; the design README's wording for the
backlog page.
