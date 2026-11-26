# A review's checks are really checked (sprint 66, after an independent review)

- A cited command counts only when it ran as a whole command, program and arguments word for word (option flags, a `cd`, a pipe, a redirection and a shell wrapper do not matter). `echo pytest x`, `grep 'pytest x'` or one test file no longer count as running `pytest x` or the suite.
- A replay that resumes the review's session is checked against the whole session's commands; it was not checked at all.
- The reviewer's prompt states its own role's rule. A role that cannot run commands cannot ask for `ran`. A reviewer role written before criteria had a basis is taken on its word instead of never approving.
- A verdict must list each of the task's criteria once, by its text; a bullet that wraps is one criterion.
- `{previous_output}` is the developer's report for reviewers only; other roles keep the last run's words.
