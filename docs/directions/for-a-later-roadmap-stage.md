# For a later roadmap stage, kept so nothing is lost

- Date: 2026-11-23 (checked against the code)
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.
- Stage 6 and the owner directions are in the files of this folder; Stage 2 is also in `the-manager-and-people.md`.

- **Stage 2:**
  - sign-in and a user's name on every decision;
  - the manager's conversations per user, with a turn lock, a kill when
    the user disconnects, and a cost per turn;
  - notices by email or chat, and replying from them (today: webhooks
    only).
- **Stage 3:** a planner step per task, with criteria and a protected test
  written by someone other than the developer.
- **Stage 6 and the owner directions:**
  - parallel workers and a container per task (the sandbox's first cut is
    ADR-0023);
  - pull requests (no code opens one today);
  - Codex as a real second harness, with a smoke test;
  - multi-repository projects, a price table for other endpoints, budgets
    per day;
  - raw output capped and redacted in a table of its own, and records kept
    apart from telemetry;
  - response models on the API, and a deployment guide.
