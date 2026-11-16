# ADR-0027: A workflow is sound before it is saved

- **Status:** accepted
- **Date:** 2026-11-16
- **Sprint:** 60

## Context

A workflow is a state machine: steps, and routes from one step to another on
the way a step ended. A task starts at the first step and follows routes.
The loader checked each route (it names real steps, and an outcome the
step's role can produce) and nothing about the whole. On 2026-11-16 eight
malformed workflows were given to it and all were accepted: a step nothing
leads to, no step that marks the task done, done without a merge, a merge
before any test, a reviewer as the first step with a merge after it, two
merges, mark-done as the first step. One of them was the "empty workflow"
the dashboard had offered since that morning (develop, then done).

Such a workflow fails late. The completion guard blocks the task at the
merge or the done step, after the agents have been paid for; with tests and
review but no merge, the task is marked done and its branch is never merged.

## Decision

`WorkflowDefinition.validate` also checks the whole, and a workflow that
fails is not loaded and not saved, from the dashboard, a TOML file or the
terminal alike:

1. The first step, where a task starts, is not the merge or the step that
   marks the task done.
2. Every step is reached from the first step.
3. A step marks the task done, and from every step that step can be reached.
4. The end is reached only through a successful merge. A task cannot finish
   with its work unmerged. A kind of task that produces nothing to merge
   will need a decision of its own.
5. A merge is reached only with the tests having passed since the last step
   that may have changed the code: an agent step that does not end in a
   decision. This is checked from the first step and from every such step.

Each refusal names the step and the path that breaks the rule.

Not checked here, because it depends on a project's settings and the
completion guard decides it when the task runs: that a review or a judge
has covered the acceptance criteria before the merge.

The dashboard's empty workflow is the shortest one that finishes a task in
a project as it is set up by default: develop, test, review, merge, done.

## Consequences

- A project's own workflow saved before this that breaks a rule no longer
  loads; its project says why when its definitions are read.
- An outcome with no route is still allowed: it means the task stops for a
  person.
- The editor can be built on these rules: a list that is a true sequence,
  with the exceptions declared.
