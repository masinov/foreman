# PR Summary: fix/run-story-folding

## Summary

- One rule for long text in a run's story (owner, 2026-11-21). What an
  agent or a user wrote is shown whole. Code and what a program printed (a
  command the agent ran, a tool's result, test output, an error) show
  their first three lines, with "Show all".
- Before, four rules were mixed:
  - an agent's words folded after twelve lines on screen;
  - tool results and merge errors were cut to three lines with no way to
    open them;
  - test output scrolled in a box;
  - long commands and some errors were shown whole.

## Scope

- `LongText` gains `brief` (three lines) and `output` (three lines,
  monospace, quieter, a `pre`).
- `RunLine` uses them for every line that is not someone's words. It
  serves both the task's Activity and the Agent side bar.
- `sayEntry` loses its `clamp` flag.
- Removed: `.run-line__result`, `.run-line__output`, `--run-result-lines`,
  `--run-output-max-height`.

## Files changed

- `frontend/src/ui/LongText.jsx` and its test
- `frontend/src/pages/task/RunStory.jsx` and `RunStory.test.jsx` (new)
- `frontend/src/pages/task/runWords.js` and its test
- `frontend/src/styles/{ui,task,tokens}.css`
- `docs/design/dashboard-v7/README.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- Test output opened with "Show all" is shown in full on the page; it no
  longer scrolls in a box. "Show less" closes it again.

## Tests

- `npx vitest run`: 473 passed
- `npm run lint`, `npm run build`: clean
- Looked at ASS-10's develop run on a copy of the live database: the
  agent's closing message whole, the 40-line `cat > … <<'EOF'` command,
  the file listing and the test dots each at three lines with "Show all".

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- The same kind of text behaves the same way everywhere in a run's story.
- Nothing is cut without a way to open it.

## Follow-ups

- The raw output and the prompt as Copy and Download buttons (backlog).
