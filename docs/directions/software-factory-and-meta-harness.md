# Foreman as a software factory and a meta-harness; the base work

- Date: owner directions, 2026-11-18
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.
- The ten numbered directions that followed in the same section are the files linked from `README.md` in this folder.

Recorded so they are not lost. Each one gets an ADR before any code. Sprint
60 and the remaining base work come first. Feature 1 is the next line of
work after that.

What they serve: Foreman as a software factory and a meta-harness. It
coordinates several harnesses and models, each with its own strengths and
prices. Its many thin arms work through existing tools (CI/CD, clusters,
trackers, identity) rather than rebuilding them. Before each arm's ADR,
survey the existing tools.

Base work that this framing makes necessary:

- **Outcome numbers per project, model and role:** first-pass success,
  send-backs, interventions by a person, and cost per merged task. These
  show whether routing between models pays.
- **Codex as a real second harness:** a smoke test against the real
  program, its cost recorded, and the same kind of task run through both
  harnesses.
