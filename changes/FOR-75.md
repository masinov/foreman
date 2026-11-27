The review sandbox is enforced

- A role with `run_scope = "none"` is refused Bash, whatever its tool list says.
- A push from a sandbox cannot reach a remote: a push to an address goes nowhere, and a push to a configured remote is refused and fails the step, so it is on the task's record.
- A sandbox left by an engine killed hard is removed when an engine starts for the project again.
- The MANUAL says what a reviewer can read in a sandbox: the paths the project links, and never a server's admin login.
