# Operating decisions

Decisions the owner made about how the work is run, as of 2026-11-10 (the
identity line was updated 2026-11-19). Moved from `docs/STATUS.md` on
2026-11-26. Decisions that bind the code are ADRs; these are about method.

- Claude drives the work. Whether a slice runs by hand or through Foreman is
  decided per slice; cost and safety observations from Foreman runs are
  recorded in the sprint doc.
- No notification channel is being chosen now. On identity the owner
  decided on 2026-11-19 that Foreman gets a simple identity system of its
  own (roadmap stage 2), which a company-wide one can replace later. This
  supersedes the 2026-11-16 line that no login or user work was planned.
- Codex stays in the tree but is treated as experimental until it has a
  shipped role, cost accounting and a real-binary smoke test.
