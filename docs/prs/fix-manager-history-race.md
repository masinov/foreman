# PR Summary: fix/manager-history-race

## Summary

- CI failed on `faf6074` (`Planning.test.jsx`, "Plan this sprint"). The side
  bar re-reads the conversation, and a reading requested before a message
  was sent could arrive after its reply ended. It then replaced the message
  and the reply with the older history. In use, that hid a just-finished
  reply until the next re-read.
- The stream now starts with `{"type": "turn", "message_id", "reply_id"}`.
  The side bar keeps what it sent until a page of history holds those ids.

## Scope

- `foreman/meta_agent.py`, `frontend/src/pages/manager/useConversation.js`,
  `frontend/src/api/manager.js`

## Files changed

- the above; tests: `tests/test_meta_agent.py`,
  `frontend/src/pages/manager/ManagerPanel.test.jsx`

## Migrations

- none

## Risks

- none known

## Tests

- ruff; full Python suite (1568); frontend lint, the suite three times and
  once on one worker (448), build. The new test fails on the previous code.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A reading of the conversation that arrives after a reply it does not
  hold leaves the message and the reply in place.

## Follow-ups

- none
