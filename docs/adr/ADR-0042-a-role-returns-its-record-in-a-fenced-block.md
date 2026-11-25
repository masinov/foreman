# ADR-0042: A Role Returns Its Record In A Fenced Block

- **Status:** accepted (ADR-0041 section 2 and the Sprint 63 task "A step's
  result is a record its role declares" ask for it; ADR-0041 left the form
  open, "a fenced JSON block, or the backend's structured output")
- **Date:** 2026-11-25
- **Sprint:** 63
- **Extends:** ADR-0041 section 2 (step results are records), ADR-0040 (the
  developer's report), ADR-0024 (a project's roles live in the database).
- **Number:** the usual next number for now; numbering happens at merge
  (ADR-0040).

## Context

A step's result passes to the next step as free text. ADR-0041 section 2
makes it a record the role declares: a kind and named fields. The record
must reach Foreman in a form it can parse reliably from both first-class
backends, Claude Code and Codex.

## Decision

### How the agent returns it: a fenced JSON block in the final message

The record is one JSON object in a fenced block whose info string is
`foreman-record`, in the agent's final message, before the completion
marker:

````
Words that summarise the work.

```foreman-record
{"summary": "...", "criteria": [...], ...}
```
TASK_COMPLETE
````

Chosen over the backend's structured output because:
- it works the same on both backends, through the one place Foreman already
  reads, the final message (`foreman/engine/output_contract.py`);
- a role's TOML stays the whole definition of the step, so a project's own
  role stored in the database (ADR-0024) can declare a record with no code;
- it needs no change to how a runner is launched, and a session that is
  resumed returns the record the same way.

The distinct info string keeps a record apart from any other JSON an agent
quotes. The last such block of the final message counts. The words around
the block stay the step's `outcome_detail` (the record's `summary` field
when there are none), so the free text keeps working for any later step that
carries it.

### How a role declares it

```toml
[completion.record]
kind = "developer_report"

[[completion.record.fields]]
name = "summary"
type = "text"
required = true
description = "What changed and why."
```

- `kind` and each field `name` are lowercase names. Every field says its
  `type` and `required`; `description` is optional and is shown to the agent.
- Types: `text` (required means not blank), `bool`, `text_list` (required
  means the key is present; an empty list says there is nothing to list),
  `choice` (one of the field's own `choices`) and `records`, a list of
  objects described by the field's own `fields`. A record's entries do not
  nest further.
- A field not declared is refused, so a typo is not stored.
- A role that returns a decision (a reviewer) may declare a record too; the
  verdict record is described in "The reviewer's verdict" below.
- The loader (`foreman/definitions/records.py`) refuses a malformed
  declaration with a message naming the role file, the field and what is
  wrong. The role's prompt takes `{record_format}`, which Foreman fills with
  the field list and an example block from the declaration, so the prompt and
  the check cannot drift apart.

### What Foreman does with it

1. **Check.** The final message is read after the marker check. A missing
   block, JSON that does not parse, or a record that breaks the declaration
   makes the step's outcome `error`. The detail starts "The step's record is
   not usable" and says what is wrong ("`criteria[1].verified` must be true or
   false"). It is routed as any error is.
2. **One correction.** As for a missing marker, the agent gets one corrective
   retry that resumes its session and says the shape again, before the error
   stands.
3. **Store.** A well-formed record is stored on the step's run in
   `runs.record_json` (migration 30) as `{"kind", "fields"}`. A run of a role
   with no record, and every earlier run, has none.
4. **Return.** `GET /tasks/{id}/runs` carries `record` on each run (the task
   detail's run list too).
5. **Hand on.** A later step receives the record as structured sections. A
   reviewer's prompt takes `{developer_report}`: the newest developer report
   of the task, criterion by criterion (`foreman/engine/report_words.py`); with
   none (a role that declares no record, or an older task) it is the
   developer's free text, as `{previous_output}` was.

### The developer's report

The shipped developer declares `developer_report` with the parts ADR-0040
lists: `summary` (what changed and why); `criteria`, one entry each with
`criterion`, `verification` (the command and its output, or a screenshot
path) and `verified`; `not_verified`; `beyond_task`; `docs_touched`;
`follow_ups`. The code, security, triage and frontier reviewers receive it
in their prompts. The task page shows it in the develop step's details.

## Consequences

- A role that declares no record behaves exactly as before, including a
  project's own roles in the database.
- A developer role copied into a project before this change keeps its old
  prompt and produces no record; its reviewers read its free text.
- The report is the developer's claim. Checking it against the change and
  the criteria is the reviewer's verdict (the next task), and the report's
  `criteria` entries are not yet compared with the task's own list.
- The block is text an agent writes, so a very long record is a long message.
  The agent's own output limit is the only bound for now.

## The reviewer's verdict (amendment, Sprint 63)

Every shipped reviewer (`code_reviewer`, `security_reviewer`,
`triage_reviewer`, `frontier_reviewer`) declares a record of kind
`review_verdict` and still ends its message with its decision line. The
record is read first (the decision is read outside the block), then checked
against the decision.

### The record

- `criteria`: one entry for each acceptance criterion, with `criterion`,
  `status` (`verified`, `not_verified` or `judgement`: the reviewer's own
  reading) and `evidence` (what it checked).
- `findings`: each with a `severity` and the `finding`, an empty list when
  there is nothing. The prompt defines the severities: S1 broken, unsafe or
  data-losing; S2 an acceptance criterion not met; S3 should be fixed, does
  not block; S4 a nit.

### Foreman checks that the verdict and the outcome agree
(`foreman/engine/verdict.py`)

- `deny` or `steer` needs at least one S1 or S2 finding.
- `approve` needs no S1 or S2 finding, and every criterion `verified` or
  `judgement`.
- `escalate` hands the decision on and is not checked.
- A verdict that disagrees with its outcome makes the step's outcome `error`,
  with a detail starting "The review's verdict does not agree with its
  outcome" and the reason. The record stays on the run, so the page shows what
  the reviewer returned. The step gets the one corrective retry that a
  malformed record gets, with the rule said again.

So only a serious finding sends work back: a reviewer cannot deny over a nit.

### Decision: S3 and S4 findings stay with the review; they do not become tasks

The findings of an approving review are kept in the review run's record
(`runs.record_json`) and shown on the task page, in the review step's
details, with their severities. Foreman does not file them as follow-up
tasks:

- a reviewer's signals are `progress` and `blocker` only (reviewers cannot
  create tasks), and an automatic task for each nit would fill the backlog
  with work nobody asked for and nobody ranked;
- S3 and S4 are the reviewer's opinion, by definition not blocking; a person
  or a manager who reads one and agrees files the task, with the finding
  already in front of them.

Revisit this if findings pile up unread: the record is structured, so a
later step could turn S3 findings into proposed tasks for a person to confirm.

### Consequences

- A project's own reviewer role in the database that declares no record
  keeps working as before: nothing is checked and no verdict is stored. A
  shipped reviewer copied into a project before this change is such a role.
- The criteria entries are not compared with the task's own list: an
  approving verdict with no criteria entries passes the check. The prompt
  asks for one entry for each criterion; comparing is a later change.
- The completion evidence the reviewers read no longer mentions a judge
  model (removed 2026-11-19); it states the branch head, the tests and the
  latest code review, and says nothing but the reviewer has checked the
  criteria (`foreman/engine/evidence.py`).
- Review rounds are not capped here (ADR-0041 section 3).

## Amendment, 2026-11-25: after an independent review, before the code went live

Sprint 63's own reviews approved in seconds, so Claude had FOR-61 and FOR-62
reviewed against their criteria before the live engine ran them. These
rules changed:
1. **The last record block that is a JSON object counts.** A later block
   that is not JSON is a quote: an agent showing the format, or a file it
   edited. Before, it replaced the record and failed the step. Windows line
   endings are read.
2. **A choice is matched without regard to case,** and stored as declared:
   a severity written `s2` is `S2`. Before, it was a malformed record, and
   the agent's one correction was spent on it.
3. **The format example never shows a blocking finding.** It shows the
   last choice of a list (S4, judgement). An example of S1 had reviewers
   copy it into an approval.
4. **A retry for a missing completion marker asks for the record too.**
   Before, it asked for the summary and the marker only. The answer then
   had no record, and the task blocked where it used to recover.
5. **An approval must list the task's criteria when the task has any.**
   An approving verdict with an empty `criteria` list passed before, so the
   per-criterion check could be skipped. Entries are still not compared one
   by one with the task's text.
6. **A review that sends work back hands the developer its S1 and S2
   findings,** after the reason. Before, the developer got the one-line
   reason only.
7. **A project's role that declares a `developer_report` of another
   shape** no longer breaks every later prompt of the task. Its report is
   left out of those prompts.
