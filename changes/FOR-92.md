A review says how it verified each criterion, and Foreman checks what it can

- Each criterion of a reviewer's verdict records its basis: the commands it ran, the files it read, and whether it relied on the developer's report.
- A command the verdict cites that the review did not run makes the verdict disagree with its outcome, with the reason.
- A reviewer role's `approve_needs` (`checked` by default, `ran`, `stated`) sets what an approval needs of each criterion; a criterion resting only on the developer's report is not verified. It is set in Settings › Roles, "An approval needs", for the workspace and for a project.
- The task page shows each criterion's basis in the review step's details and marks the commands Foreman saw run.
