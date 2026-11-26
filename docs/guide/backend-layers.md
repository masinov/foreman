# The backend is laid out in layers

Moved from `docs/STATUS.md` on 2026-11-26 (ADR-0032, slice 14 of sprint 61's
plan, owner, 2026-11-19).

- `.importlinter` states the stack and CI holds it, with no exception.
- It landed in five branches that changed no behaviour. Every module path
  changed: a branch opened before 2026-11-19 must be rebased, and a process
  started before then must be restarted.
- Every change the CLI and the services make goes through
  `foreman.mutations` (`tests/test_layers.py`).
- The five longest modules are packages split by concern.
- Left, in ADR-0032: the CLI's reads are its own, and seven functions are
  over 200 lines.
