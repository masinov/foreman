# PR Summary: refactor/layers-notifications

## Summary

- Slice 5 of ADR-0032, the last of its plan. `notifications` is a package
  split by concern, and imports are at the top of their module.
- ADR-0032 is brought to its end state and lists what the layers do not yet
  settle.

## Scope

- `foreman/notifications/`: `policy` (whether to speak), `destinations`
  (where, checked before saving), `transport` (the payload and the webhook),
  `delivery` (the dispatcher's queue and the delivery worker). The logger is
  still `foreman.notifications`.
- 42 imports moved from inside functions to module level, by a script. Three
  are left: `uvicorn` (starting the server), `httpx` (the judge's call) and
  `ctypes` (Linux process control).
- The four `if TYPE_CHECKING:` imports, said to break cycles, are plain
  imports. None of them was a cycle under the layers.
- `ruff`'s import sorting is applied to the modules this branch touched.

## Files changed

- `foreman/notifications/*`, 16 modules whose late imports moved, the four
  former `TYPE_CHECKING` modules, the importers of `notifications`.
- ADR-0032 ("Where things went (slice 5)", "What the layers do not settle
  yet"), `docs/ARCHITECTURE.md`, `docs/STATUS.md`,
  `docs/sprints/current.md` (slice 14 done), `CHANGELOG.md`.

## Migrations

- none

## Risks

- Moving an import to module level makes a missing optional dependency fail
  at import rather than at use. None of the moved imports is optional: they
  are Foreman's own modules and the standard library.

## Tests

- full Python suite, ruff, `lint-imports`, repo-memory validation; each
  entry module imported in a fresh interpreter.

## Acceptance criteria satisfied

- Nothing but `__init__` and `__main__` is at the root of `foreman/`.
- The contract keeps with no exception.

## Follow-ups

- The CLI through the services (ADR-0032, "What the layers do not settle
  yet").
- The five long modules, a part per concern.
