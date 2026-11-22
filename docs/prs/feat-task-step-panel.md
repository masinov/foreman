# PR Summary: feat/task-step-panel

## Summary

- A task's picked step has one shape for every kind of step, built from the
  mockup the owner chose (2026-11-22):
  - **Left, what happened in order.** Each line is a time, what happened
    in plain words, and what it ran (first lines), wrote (whole, formatted)
    or printed (last lines). An agent's step begins with "Sent the prompt
    · N lines".
  - **Right, the step's facts.** Result, Why, Decided by, After, the commit
    it was about, By, Model, May use, Took, Spend, Next. After and Next
    pick that step in place.
  - **One button,** "Download the transcript".
- The story leaves out the step's bookkeeping, events with no words, and
  JSON.
- Agents' decision words and completion markers are dropped from their
  text, and Markdown is formatted.

## Scope

- Frontend only; the API already returned the prompt, the transcript and
  the raw stream.
- `pages/task/stepFacts.js` (new) works out the facts from the run and its
  transcript.
- `ui/Markdown.jsx` (new) formats paragraphs, nested lists, headings,
  fenced code, bold and code, into elements, never HTML.
- `runWords.js`:
  - more silenced events;
  - unknown events are no longer printed as JSON;
  - `ownWords` drops the markers;
  - a refused tool reads as such;
  - tool input shows as values;
  - a gate decided by the setting says so.
- `RunStory.jsx`: what was run folds from the top; what was printed shows
  its last lines.
- `ActivityTab.jsx`:
  - the panel's two columns;
  - the transcript download, which reads the raw stream only when asked
    for;
  - "Show the raw output", "Show the prompt" and "No prompt was recorded"
    are removed.
- The Agent side bar's story follows the same rules (it shares `narrate`
  and `RunLine`).

## Files changed

- `frontend/src/ui/Markdown.jsx` (new)
- `frontend/src/pages/task/stepFacts.js` (new)
- `frontend/src/pages/task/{ActivityTab,RunStory}.jsx`
- `frontend/src/pages/task/runWords.js`
- Tests:
  - `frontend/src/pages/task/{TaskPage,RunStory}.test.jsx`
  - `frontend/src/pages/task/runWords.test.js`
- `frontend/src/styles/{task,ui}.css`
- `docs/design/dashboard-v7/README.md`, `CHANGELOG.md`,
  `docs/sprints/backlog.md`

## Migrations

- none

## Risks

- A completion marker is any final line of three or more capitals, digits
  or underscores ("TASK_COMPLETE"), because a role can name its own. A
  message whose real last line is such a word loses it on the page; the
  transcript keeps it.
- Events the page has no words for are left out of the story. The
  transcript download keeps them.

## Tests

- `npx vitest run`: 477 passed
- `npm run lint`, `npm run build`: clean
- Looked at ASS-16's steps on a copy of the live database, at 1440 and
  390 px:
  - Develop attempt 2
  - the review that sent it back
  - Merge approval decided by the setting
  - Test attempt 2
  - Merge

## Screenshots or output examples

- n/a (the steps above, in the conversation)

## Acceptance criteria satisfied

- Every kind of step reads the same way: lines on the left, facts on the
  right.
- No JSON, event names, markers or bookkeeping in the story.
- The prompt is an ordinary first line; one download button.

## Follow-ups

- In the backlog ("A task's Activity, step by step"):
  - the table
  - facts that need the repository
  - recording the test count and the start of a test run
  - storing sprint and engine records apart from tasks
