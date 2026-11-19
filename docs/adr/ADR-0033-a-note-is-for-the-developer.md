# ADR-0033: A note is for the developer

- **Status:** accepted
- **Date:** 2026-11-19
- **Sprint:** 60 (decision 6)

## Context

A person steers a task by writing a note on its page (Tell the agent). The
note was put into the prompt of the next agent step, whichever role that
was, and marked delivered there. Two things went wrong with that, both
pointed out by the owner:

- A note written while the task waited for review went to the reviewer,
  verbatim, as instructions, although it was meant for the developer. The
  developer then never got it.
- A note that changed what was wanted ("leave the API alone, only the UI")
  never reached the reviewer once the developer had it. The reviewer then
  reviewed against the original task and could refuse work that did what the
  person asked.

## Decision

**A note is for the agent doing the work.** It is delivered only to a role
whose run does not end in a decision (`completion.output.extract_decision`
false; the developer in every shipped workflow). It waits for that role's
next step and is marked delivered there.

**A reviewer is shown every note as context, and is delivered none.** Its
prompt has a section "What a person told the developer" with each note and
whether the developer has had it yet. It says they are not instructions to
the reviewer, and that a note the developer has not had cannot be in the
work yet.

"Interrupt and tell it now" is unchanged: it is a person addressing the
agent that is running at that moment, whichever role it is.

The dashboard says who a note is for: "Save for the developer", and a note
not yet read is "Waiting for the developer's next step".

## Consequences

- A note written while a task is past its last development step (at merge
  approval, say) waits until the task is sent back to development. The task
  page shows it as waiting, as before.
- Roles are told apart by what their run produces, not by their id, so a
  project's own roles follow the same rule (ADR-0024).
