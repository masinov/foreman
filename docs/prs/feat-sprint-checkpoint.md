# PR Summary: feat/sprint-checkpoint

## Summary

- Sprint 62, slice 2: a finished sprint is tagged, and given a note where
  the project asks for one (spec 6.4, ADR-0036).
- It works the same whether a user finishes the sprint (dashboard,
  `foreman sprint complete`, a manager's proposal) or Foreman does.
  - **The tag:** the default branch's head gets an annotated tag,
    `checkpoint-YYYYMMDD-<sprint-title>`. A name already taken gets `-2`.
  - **The note:** with "Checkpoint note: Write one" (`write_checkpoint_notes`),
    a note is committed first to `docs/checkpoints/<tag>.md` on the default
    branch. It lists the goal, the tasks done and cancelled, and the
    follow-ups agents filed. The project's checkout on that branch follows
    the commit (ADR-0031).
  - **The push:** both go where merges are pushed (`merge_push_remote`).
  - **The records:** `engine.checkpoint`, or `engine.checkpoint_failed`
    with the reason. The sprint stays finished either way.
- **Shown:**
  - Tag and Note rows in the sprint's Details;
  - "Not tagged:" and why, when it failed;
  - the "Checkpoint note" choice in Settings › General › Advanced;
  - the tag and note printed by `foreman sprint complete`.

## Scope

- **New:** `foreman/mutations/checkpoint.py` (`SprintCheckpoints`).
- **Callers:** `foreman/mutations/sprints.py` (`transition_sprint`) and
  `foreman/engine/sprints.py` (`SprintFlow`).
- **Git:** `foreman/repo/git.py`: `tag_commit`, `create_tag`, `push_tag`.
- **Setting:** `foreman/domain/settings.py`: `write_checkpoint_notes`, true
  or false.
- **Reads:** `foreman/services/sprints.py` (`checkpoint` on the sprint) and
  `foreman/cli/sprints.py`.
- **Frontend:**
  - `pages/sprint/SprintHead.jsx`;
  - `pages/settings/{settingsForm.js,settingsWords.js,GeneralTab.jsx}`;
  - `pages/task/runWords.js`: a pushed tag in a step's story.

## Files changed

- As in Scope.
- **Tests:**
  - `tests/test_sprint_checkpoint.py` (new);
  - `frontend/src/pages/sprint/SprintPage.test.jsx`;
  - `frontend/src/pages/settings/ProjectSettings.test.jsx`;
  - `frontend/src/testing/settingsFixture.js`.
- **Docs:**
  - ADR-0036 and `docs/adr/README.md`;
  - `docs/MANUAL.md`, `docs/design/dashboard-v7/README.md`;
  - `docs/STATUS.md`, `docs/sprints/{current,backlog}.md`, `CHANGELOG.md`;
  - `docs/prs/docs-assay-test-reports.md`, left out of that branch.

## Migrations

- None. The setting defaults to off. Sprints finished before this slice
  have no tag, and are not tagged now.

## Risks

- With a push remote set, finishing a sprint from the dashboard waits for
  the push, as a merge does.
- **Where the records go.** They are kept on a run of the sprint's first
  task, like every sprint record today. A sprint with no tasks keeps none.
  Slice 3 stores sprint records as what they are.
- **Hooks.** A project whose commit hooks refuse the note gets "Not tagged"
  and the reason. The note's file is removed again.

## Tests

- `tests.test_sprint_checkpoint` (11), with real git repositories and a bare
  remote:
  - a user's finish and Foreman's finish;
  - the note and its contents;
  - the checkout following the note's commit;
  - pushing;
  - a taken name, the same completion recorded once, a missing branch;
  - a proposal's deferred side effect, the setting's validation, the CLI's
    lines.
- The whole Python suite, `npm test`, `npm run lint`, `npm run build`,
  ruff and `lint-imports`.

## Acceptance criteria satisfied

- Spec 6.4 steps 2 to 4 happen on every finish, and say so where the
  sprint is shown.

## Follow-ups

- Slice 3: sprint and engine records stored apart from tasks; the project's
  Activity lists "Sprint finished · tagged …".
