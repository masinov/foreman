# ADR-0028: Foreman starts backlog work, and acceptance is its permission

- **Status:** accepted
- **Date:** 2026-11-16
- **Sprint:** 60

## Context

The owner pressed Accept on a backlog task and asked what it had done. It had
changed a status and nothing else. Traced end to end (and read independently
by a second agent):

- In ADR-0014 accepting a filed task released it to run. ADR-0021 then put
  the backlog and a person-only Plan step after it and kept Accept
  unchanged. The gate lost its consequence, and the step that releases work
  had no policy.
- No path ran filed work without a person planning it: not "Accept filed
  work: Foreman", not autonomous task selection, not the manager.
- Autonomous task selection (spec §6.2) created an empty placeholder task
  for the agent to name with `signal.task_started`. It never read the
  backlog and never selected a task a person had planned. The signal let an
  agent set any task's title, type, branch and acceptance criteria.
- A task a person filed from the dashboard or the terminal had to be
  accepted by a person.

Both readings came to the same rule: acceptance either has something that
uses it or it goes. The owner chose to give it a use ("B now").

## Decision

1. **Autonomous task selection means: Foreman starts backlog work on its
   own.** Planned work runs first. When nothing planned can run, the engine
   takes the next accepted backlog task (higher priority first, then the
   order filed, dependencies done) into the active sprint and runs it, up to
   `max_autonomous_tasks` per sprint. The move is made as `foreman` via
   `policy` and recorded as `engine.task_pulled`, which is what the limit
   counts. With no active sprint, or an empty backlog, it does nothing.
2. **The placeholder mode and `signal.task_started` are removed.** Foreman
   invents no tasks. If agents are to propose work they file it
   (`signal.task_created`), like anyone else.
3. **A request is work an agent or another system filed that no person has
   accepted** (status `triage`). Accepting it means "Foreman may start this
   on its own". The engine never takes a request. A person planning a
   request into a sprint accepts it by doing so. Foreman acting by policy
   may not plan one.
4. **What a person files is never a request.** The filer is told apart by
   the role the write is made under (`human`), not by a flag the caller
   remembers to pass.
5. **The triage policy keeps its name and gains its meaning:** `human`,
   requests wait for a person; `auto`, what agents and systems file is
   backlog work at once, and in autonomous mode Foreman starts it with
   nobody pressing anything.
6. **The dashboard asks for acceptance only where it has an effect.** In a
   directed project there are no requests to answer: the backlog is one
   list, and a task is planned into a sprint or declined. In an autonomous
   project whose triage policy is `human`, requests are listed apart with
   Accept, and one "Needs you" line per project counts them.
7. **Turning autonomous mode on blesses nothing.** Requests stay `triage`
   in the data whatever the mode, so work nobody looked at cannot become
   work Foreman starts by a setting being changed.

## Consequences

- The limit per sprint is the bound on the loop "an agent files work,
  Foreman starts it, it files more": each turn uses one.
- Per sprint is the wrong unit for a project that keeps one standing sprint
  fed by intake; that may need a limit per day. Not decided.
- Foreman does not open a sprint. With none active, backlog work waits.
- Not done here: a cap on how many tasks one agent step may file, refusing
  a filing that repeats an open or declined one, showing which task an
  agent was working on when it filed another.
- Spec §6.2 is revised with this ADR. ADR-0014's description of `triage`
  and ADR-0021's "Accept, unchanged" are superseded by decisions 3 to 6.
