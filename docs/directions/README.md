# Directions

The owner's directions and the design decisions taken with the owner, one file
each. A file keeps its date and the owner's words exactly as they were said or
written, so a later reader sees what was asked and when, not a summary of it.

Foreman's backlog is the work to do (`docs/sprints/backlog.md` is a copy of it,
written by Foreman). A direction is not a task: when one becomes work, a task is
filed in the backlog and names the file; the file stays as the reason.

## How to add one

- One file, `docs/directions/<slug>.md`, with a title line and a `- Date:` line
  (who said it, and when).
- The owner's words go in as written, between quotation marks or as a quoted
  block. What Claude added (a survey, a conclusion, a proposal) is marked as
  Claude's, with its date.
- A later decision about the same thing is added to the same file under its
  own date; the earlier words stay.
- Say which ADR a direction led to once there is one, and link it.

## The files

The manager, people and who decides:

- [The manager and people](the-manager-and-people.md) (2026-11-19)
- [Foreman as a software factory and a meta-harness; the base work](software-factory-and-meta-harness.md) (2026-11-18)

The roadmap's later stages (2026-11-18):

- [One central server, with workers on other machines](central-server-and-workers.md)
- [Shared compute, through a cluster manager](shared-compute-through-a-cluster-manager.md)
- [Releases and deployment, through existing CI/CD](releases-and-deployment-through-ci-cd.md)
- [Workflows above the task](workflows-above-the-task.md)
- [For a later roadmap stage](for-a-later-roadmap-stage.md)

Tests and how work runs:

- [Tests that are designed, not only watched](tests-designed-not-only-watched.md)
- [Test tiers and a parallel suite](test-tiers-and-a-parallel-suite.md)
- [Several tasks at once in one project](several-tasks-at-once.md)
- [Dependencies across sprints](dependencies-across-sprints.md)
- [Which models and harnesses run which work](models-and-harnesses-set-by-the-user.md)
- [The size label goes, and a step moves up only after failures](the-size-label-goes-and-a-step-moves-up-after-failures.md)

The dashboard and its views:

- [The views, thought through as one system](the-views-as-one-system.md)
- [A task's Activity, step by step](a-tasks-activity-step-by-step.md)
- [The sprint page, step by step](the-sprint-page-step-by-step.md)
- [Activity, one stream at three depths](activity-one-stream-at-three-depths.md)

The repository and the agents' view of it:

- [How a project's repository is organised](how-a-repository-is-organised.md) (ADR-0040)
- [A code map for agents](code-map-for-agents.md)
- [Statuses stay strings](statuses-stay-strings.md)
- [A memory Foreman keeps, and loads into each step](a-memory-foreman-keeps-and-loads.md) (2026-11-27)

Other projects:

- [Assay and Foreman: an evidence base that feeds projects](assay-and-foreman.md) (2026-11-26; Assay serves any client, 2026-11-27)
