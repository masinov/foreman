# A memory Foreman keeps, and loads into each step

- Date: owner, 2026-11-27; Claude's notes the same day
- Roadmap: stage 9 (`docs/ROADMAP.md`); its first step is the escape log
  (ADR-0040 item 9, sprint 70 in the timeline).

## The owner's words

After Claude found, preparing FOR-73, that Foreman's agents were given the
operator's own Claude Code memory:

> "you raise an interesting point. Persistent memory repository and memory
> loading are interesting features to add."

## What was found (2026-11-27)

Claude Code keeps a memory per person and repository
(`~/.claude/projects/<repository path>/memory/`): an index file loaded at
the start of every session, one file per fact. An agent Foreman starts in a
task worktree was given that index, because the worktree belongs to the same
repository. It is the operator's memory, written for their own sessions.
FOR-73 turns it off for agents.

## Claude's notes (2026-11-27), for the ADR of stage 9

Two kinds of memory, kept apart:
- **A person's own memory** stays theirs, and never reaches agents.
- **A memory that Foreman keeps** belongs to the project (or to the
  workspace, or a role), and Foreman loads it into the steps it is for.

What the memory Foreman keeps could be, following decisions already taken:
- **A record, like the rest of Foreman's state:** in the database, each entry
  with who wrote it, when, from which task or review, and what it rests on.
  Nothing is overwritten, so what an agent was told on a given day can be
  answered. Markdown copies, if any, are generated (ADR-0040).
- **Agents propose and people settle,** as in Assay: an entry written by an
  agent (a lesson from a send-back, a pattern seen in reviews) is a proposal
  until a person, or a project policy, accepts it. A wrong lesson in memory
  steers every later task, so this is a gate.
- **Loaded by scope, as a pointer layer** (ADR-0041 §6): workspace, project,
  role and step each get what applies to them. The index is short, and each
  entry is read when the step needs it.
- **Kept current:** an entry names the documents or code it rests on, with
  their commit (FOR-93's mechanism), and is flagged when they change. An
  entry that no longer holds is retired, not deleted.
- **Measured:** whether a lesson in memory reduces the send-backs it was
  written for (`foreman outcomes`, ADR-0034).

Where it comes from: the escape log (a fault found after review, and the check
that should have caught it); review findings that repeat; a person's
corrections at a gate; questions answered by a person (ADR-0041 §4).

Survey before the ADR (owner, 2026-11-18: integrate before building): Claude
Code's own memory and `CLAUDE.md` layering, Codex's `AGENTS.md`, Cursor's
rules and memories, Letta (MemGPT), mem0, Zep and LangMem, and Assay's model
of a statement with its source.
