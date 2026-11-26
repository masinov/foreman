A task names the documents it rests on, with the commit it named them at

- A task has a list of documents of the repository, each a path and optionally a heading; Foreman records the default branch's commit when each is named. It is set from the task form and page, `foreman task add`, `foreman task edit` and `foreman backlog add` (`--rests-on PATH[#HEADING]`), the manager's proposals and the intake API (`rests_on`).
- A path that is not a file on the default branch is refused, with the reason.
- The task page's Overview lists them with their commits, and each opens as it was at that commit.
- Every agent step is given them as pointers (path, heading and commit, not the text). ADR-0041 section 6 is amended to say so.
