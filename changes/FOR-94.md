A task hears when a document it rests on changes

- A merge that changes a document that an unfinished task (todo, in progress, blocked or paused) rests on adds one line to that task's Activity, with the merge and the commit the task named the document at. Nothing in the task is changed and it is not stopped.
- The task page's "Rests on" says the document changed and opens the diff between the two commits; the task's next agent step is told in its context. Naming the document again clears the notice.
- `foreman task list <project> --rests-on PATH[#HEADING]` lists every task that rests on a document, finished ones included. ADR-0041 section 6 is amended.
