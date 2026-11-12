# fix/wordmark-answers-the-pointer

## Summary

The wordmark turns gold on hover and keyboard focus again. `feat/identity-icons-motion`
had removed its hover colour; the owner had not asked for that and said the
wordmark no longer read as a button.

## Scope

`frontend/src/styles/shell.css`, `frontend/src/styles/motion.css`.

## Files changed

Two stylesheets, changelog.

## Migrations

None.

## Risks

None known.

## Tests

`npm --prefix frontend test`. CSS only; a headless screenshot cannot hover,
so it was not seen.

## Follow-ups

None.
