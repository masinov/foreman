# ADR-0029: On a task page the side bar is the conversation with the task's agents

- **Status:** accepted
- **Date:** 2026-11-17
- **Sprint:** 60

## Context

The dashboard has one side bar, toggled from the top bar. Design v7 put the
project's manager in it on every page inside a project, a task page included
(`05-task-overview.html`).

Telling a task's agent something (ADR-0011 amendment, "Interrupt and tell it
now") had been built as a box on the task page: first on Overview and on
Activity at once, then pinned under the output on Activity. The owner's
objections, 2026-11-16 and 17:

- a person cannot tell what the agent is doing from the place where they are
  asked to steer it, "unlike in Claude Code";
- a box pinned to the bottom of a tab covers the tab;
- the manager works at the level of the project and the sprint, so it has no
  business on a task page, while the thing a person does want to talk to
  there, the agent doing the task, had no place.

Traced in the code: the output of a running step was read when the step's
list of runs changed, which is when a step starts or ends. While a step
printed, nothing on the page changed.

## Decision

1. The side bar is the conversation with whoever works at the level of the
   page: the manager on a project, its backlog, its settings and a sprint;
   the task's agents on a task. One slot, one toggle in the same place; the
   toggle says "Manager" or "Agent".
2. The agent conversation lists the task's steps oldest first. Each step is
   one line (step, how it ended, who, how long, cost) that opens onto what
   the agent said and did. The step in progress is open; with none, the last
   step an agent or the engine did. What a person told the agents is shown
   where it was said, with whether an agent has read it. The box to tell the
   agent something is at the bottom, and is the only one on the page.
3. A running step is followed as it prints: the app follows the project's
   event stream once (`useLiveData`) and hands every event on
   (`app/projectEvents.js`); a running step's output is read again at most
   once a second while events about its task arrive (`useTaskPulse`). The
   Activity tab's output follows the same way.
4. Open or closed stays one remembered choice for the side bar. On a task
   with a step in progress the bar is also open without being asked, where
   it sits beside the page (not where it would cover it), until the person
   closes it on that task.
5. The conversation leaves out what it says elsewhere (the lines the step's
   own line repeats, a person's note inside a run) and the runs that only
   hold a record (filed, planned, cancelled). The Activity tab stays the
   full record: every run, its whole output, the raw stream, the prompt.
6. "Split into smaller tasks" is the manager's work, so after asking, the
   person is taken to the task's sprint (or the backlog), where the manager's
   proposal appears.

## Consequences

- The manager cannot be asked about a task from the task's page. A person
  asks from the sprint. The manager's page context no longer names a task
  from the dashboard (the API still accepts `task_id`).
- `05-task-overview.html` in design v7 shows the manager on a task page and
  is not redrawn; this ADR and the design README's "Manager" paragraph say
  what replaced it.
- A person's note still reaches one agent step, the next one (ADR-0011). The
  owner was offered having it reach every later step, reviewers included,
  and has not decided.
- Not seen against a real agent yet: "Interrupt and tell it now" on a step
  that is really running. The following of output was checked in a browser
  against a copy of the database with a step replayed into it.
