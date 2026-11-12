# feat/changes-folder-breadcrumb

## Summary

The owner asked for a breadcrumb to move through a long list of changed
files, said the files seemed to change on their own, and that "Develop, by
claude-opus-5-5" is not a title.

## Scope

- `pages/task/ChangesTab`: `scopeOf(files, dir)` gives the files under a
  folder and the folders directly inside it. The list shows those folders
  (file count, lines added and removed) above the files, from ten files up
  or once inside a folder. A breadcrumb above it shows where the list is and
  goes back up. File names are shown from the current folder down.
- The same component: the first file is picked once and stays picked; the
  diff's cache key is the branch's head commit, so a running task's events
  no longer reload it. Before, with nothing picked, "the first file" was
  whatever was first after each refresh, and every event re-read the diff.
- `pages/task/ActivityTab`: the selected run's heading is the step; "by
  <who>" and the time are its note.

## Files changed

`frontend/src/pages/task/ChangesTab.jsx`, `ActivityTab.jsx`, styles, tests,
changelog.

## Migrations

None.

## Risks

While an agent is committing, the file list itself still changes as files
are added; that is the branch changing, and it is correct.

## Tests

`npm --prefix frontend test` (279 pass, 2 new). Frontend only; the Python
suite was not re-run. Seen in a screenshot on a task with 49 changed files.

`ProjectSettings.test.jsx > never sends a host-level setting` failed once in
four runs and passed alone; it is flaky and not touched here.

## Follow-ups

Fix the flaky settings test.
