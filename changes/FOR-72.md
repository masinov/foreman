# The size label goes

- A task has no size (small, medium, large). It only chose the first model of a role's ladder; a ladder now starts on its first model unless the task names one (`foreman task override --ladder-start`, or Overrides on the task page), and moves up only after failures.
- Gone from `foreman task add --complexity`, `foreman backlog add --complexity`, `foreman task edit --size` and `foreman task show`; from the New task and Edit task dialogs, the task page's details and the manager's cards; from the manager's planning prompt, its operations and the services, schemas and store. A migration drops `tasks.complexity` (a database from before it opens).
- The intake API accepts a `complexity` and ignores it, so systems that send one do not break; the MANUAL's "Intake API" says so.
