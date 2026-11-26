# The documents a task rests on: the gaps a review found, closed

- `foreman task list <project> --rests-on PATH` lists the backlog's tasks too (filed, in triage, accepted, declined), under a `Backlog:` line.
- A merge that changes a document tells tasks in triage as well, and writes one Activity line per changed file however many headings of it the task names.
- A changed document can be marked as read: "Mark as read at <commit>" beside it on the task page, or `foreman task edit <task> --restamp PATH[#HEADING]`, stamps that entry with the default branch's commit now and ends the notice. Changing only the heading keeps the commit, and the notice.
- Each entry opens at its own commit, also when one file is named under two headings (`GET /api/v1/tasks/<id>/documents?path=&heading=`).
- A manager's proposal stamps its documents when it is made, so a merge before it is confirmed is reported to the task. The proposal card lists the documents of a filed or edited task.
- Refused with the reason: a symbolic link, a project whose repository is not on the machine, a path or heading with a line break. A new sprint whose first tasks name a missing document is not made at all. A path with a `#` is written `path #heading` (or `path #`).
