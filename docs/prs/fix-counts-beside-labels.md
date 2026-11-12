# fix/counts-beside-labels

## Summary

The owner reported "Needs you 0" and "Backlog 0" as strangely aligned.

## Scope

`ui/SectionHeading`, the project and task tab counts, and their styles: the
count is 12px medium with tabular figures, 6px from the label, on its
baseline. The gap is a margin; a visually hidden space keeps the accessible
name and copied text reading "Needs you 0".

## Files changed

Three components, two stylesheets, changelog.

## Migrations

None.

## Risks

At 3x magnification the old rendering was already on the baseline here, so
what the owner saw may have been something else (their browser, their zoom).
If it still looks wrong, a screenshot from their side is needed.

## Tests

`npm --prefix frontend test`. Frontend only; the Python suite was not re-run.
Seen in a magnified screenshot.

## Follow-ups

None.
