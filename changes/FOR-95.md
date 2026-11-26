A gate decision records the version it decided on

- A merge approval records the task branch's head commit and the default branch's head; a plan approval records a fingerprint of the task's description and criteria and the run whose plan it was. Older decisions open as before (migration 35).
- An approval that names a version (`foreman approve --version`, or the task page, which names the one it showed) is refused with the reason when the branch or plan has changed since; the page then shows the new version. Without a version the decision is recorded as before, and the CLI says which version it was recorded against.
- The task's Activity line reads "Approved at abc1234", and `foreman history` shows the commits (or plan fingerprint) on the decision.
