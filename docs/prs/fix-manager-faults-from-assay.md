# PR Summary: fix/manager-faults-from-assay

## Summary

- Four faults in the manager's conversation, found when Assay was planned
  through Foreman (ADR-0022 amendment, 2026-11-18):
  1. A turn sent from elsewhere showed no sign of progress for its eight
     minutes. The reply is now stored as it is written, and the side bar
     shows it with its cursor. One message is answered at a time.
  2. A turn that crashed left the manager's process running, and it stored
     a proposal afterwards. The process now ends with the turn.
  3. Clearing the conversation hid its waiting proposals. Clearing now
     declines them, and the dialog says how many.
  4. Creating a sprint and filling it took two proposals. `create_sprint`
     and `file_task` now take a `ref`.

## Scope

- Store: `start_meta_reply`, `update_meta_turn`, `meta_reply_in_progress`,
  `close_unfinished_meta_replies`; `append_meta_turn` takes `created_at`.
- `foreman/meta_agent.py`: the reply is stored up front and saved as it
  grows; `_run_claude` kills and reaps its process in `finally`;
  `clear_session` declines waiting proposals; the operating contract
  explains refs.
- Routes: the busy guard on message, supervise and clear;
  `waiting_proposals` in history; `declined_proposals` from clear.
- `foreman/dashboard/app.py`: replies left in progress are closed when the
  dashboard starts.
- `foreman/proposals.py`: refs for every operation that creates something;
  `decline(sentence=)`; `names` entries for refs.
- Frontend:
  - `useConversation`: a stored reply in progress shows as streaming; the
    conversation is re-read while the side bar is open; earlier pages are
    kept.
  - the clear dialog names the waiting proposals;
  - the proposal card names created things by title.

## Files changed

- `foreman/store/meta.py`, `foreman/meta_agent.py`, `foreman/proposals.py`,
  `foreman/dashboard/routers/meta.py`, `foreman/dashboard/app.py`
- `frontend/src/pages/manager/useConversation.js`, `ManagerPanel.jsx`,
  `ProposalCard.jsx`, `proposalWords.js`
- tests: `tests/test_meta_agent.py`, `tests/test_proposals.py`,
  `tests/test_planning.py`, `tests/test_dashboard.py`,
  `frontend/src/pages/manager/ManagerPanel.test.jsx`, `proposalWords.test.js`
- `docs/adr/ADR-0022-…`, `docs/MANUAL.md` (§12, the API table, and the
  checkout notes ADR-0031 made wrong), `CHANGELOG.md`

## Migrations

- none. The in-progress marker lives in `meta_turns.tool_uses_json`, like
  `interrupted`.

## Risks

- The side bar re-reads the conversation every 5 s while it is open. It is
  one small query.
- A second dashboard started on the same database while the first is in
  the middle of a reply marks that reply interrupted. The first dashboard's
  final save then restores it.

## Tests

- ruff, the full Python suite, frontend lint, tests and build. Checked in a
  browser on a copy of the database: a reply in progress started from
  elsewhere, and its completion.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A reply started from elsewhere shows with its cursor, Send is held until
  it ends, and the finished reply appears without a reload.
- A second message during a reply is refused, with the reason.
- After the reading stops early, the manager's process is gone.
- Clearing declines the waiting proposals as the person's decision.
- One proposal creates a sprint and plans tasks into it.

## Follow-ups

- none
