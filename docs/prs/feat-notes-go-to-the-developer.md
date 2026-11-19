# PR Summary: feat/notes-go-to-the-developer

## Summary

- Sprint 60, decision 6 (ADR-0033): a person's note is delivered only to
  the agent doing the work. Reviewers see every note as context.

## Scope

- `domain/guidance.py`: `prompt_with_guidance_as_context`, a section "What
  a person told the developer" listing each note and whether the developer
  has had it, said not to be instructions.
- `engine/workflow_runner/agent_steps.py`: a decision role
  (`extract_decision`) gets the notes as context and is delivered none; any
  other role gets the pending notes as before.
- Task page: "Save for the developer", "Waiting for the developer's next
  step", and the send-back hints name the developer.

## Migrations

- none

## Risks

- A note written after a task's last development step waits until the task
  goes back to development.

## Tests

- `tests/test_guidance.py` (new), the engine test in `tests/test_worktrees.py`
  updated (the reviewer's prompt has the note as context), the task page
  tests (103), the full Python suite.
