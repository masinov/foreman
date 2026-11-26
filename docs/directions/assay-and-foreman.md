# Assay and Foreman: an evidence base that feeds projects

- Date: the owner, 2026-11-26; Claude's proposal with a second opinion from
  Fable, the same day.

## The owner's words

On how a project's directions are kept, after sprint 65:

> "Have you read assay? I think it more or less gives indications of how all
> of this should be handled. I don't really know how to handle assay: I think
> it makes sense for it to be a standalone project, but i also want to connect
> it to foreman precisely so evidence can be fed to projects and audited and
> turned into specs. What do you think? You can consult Fable as well."

On the proposal below:

> "Your opinion is sound, I do like it. We can start this IF we have nothing
> more pressing next."

## Claude's proposal (2026-11-26, with Fable's second opinion)

Assay is `../assay`, an evidence base built through Foreman (its spec:
`docs/specs/Evidence base specification.md` there; sprints S1 and S2 of S7
done on this date).

**Assay stays a product of its own, connected to Foreman through each side's
HTTP API.** It is not merged into Foreman:
- **Subject.** Assay holds evidence about a client's world: one isolated base
  per engagement, append-only, two clocks. Foreman holds work.
- **Authority.** In Assay, automation proposes and named people settle.
  Foreman lets policy start work (ADR-0028).
- **Reach.** Assay serves work Foreman never runs (question rounds, client
  documents, fitted models). Foreman runs projects with no client, itself
  included.
- **Assay already expects a builder.** Its agent briefing names coding agents
  as its reader. "Evidence turned into specs" is Assay's Publish operation,
  so Foreman does not build its own.

**How a project's knowledge maps onto Assay's strata:**

| Assay | Foreman |
|---|---|
| Source and assertion: who said what, exactly | The owner's words; `docs/directions/` |
| Commitment: a decision and what it rests on | ADRs |
| Publish: a document drafted from commitments, approved by a person | The spec |
| Artifact with bindings: what it rests on, by id and version | Tasks and code, which today point at ADRs "by path and heading" (ADR-0041 §6) |
| Propagation and findings: a change reaches every dependent | Backlog items filed by hand |
| Agent briefing: decided, pending, challenged | What each step is given (ADR-0041 §6) |
| "Automation proposes; named people settle" | Gates and policies |

**What crosses:**
- **Assay to Foreman:**
  - **The agent briefing is a declared step input.** The task stores the
    base, the commitment ids and a snapshot id, not the text. Only decided
    lines may become criteria; a proposal or a decision with review pending
    never does.
  - **Findings and unbuilt commitments** arrive through Foreman's intake
    (ADR-0013). Each carries `source.system = assay` and the finding's id as
    its reference. They are requests that never start on their own
    (ADR-0028).
- **Foreman to Assay:**
  - **At merge,** the merge commit and the bindings with the snapshot the
    task was given.
  - **Test runs** become check runs where a check is registered.
  - **An agent's observations** become proposed assertions by an agent
    party.
  - **An agent's question about the client's world** (ADR-0041 §4) becomes
    an Assay question, with the task as what it blocks.
- **Never:**
  - a person's Assay token inside Foreman (Foreman writes as an agent);
  - a Foreman approval or merge recorded as a client's ratification or as
    support;
  - client evidence text in Foreman's database (Foreman keeps prompts) or in
    any memory across projects;
  - Foreman's generated copies cited as a basis (Assay: no digests);
  - a shared database.

**Foreman's own memory: borrow the ideas, keep them small, no Assay base
yet.** Assay has no commitments, bindings or briefing before its S4, and
Foreman's memory must not depend on a service still being built. Three ideas
are worth taking now:
1. A task names the ADRs and spec sections it rests on, with their commit.
2. Superseding an ADR lists the tasks that rest on it.
3. An approval records the exact version of the document it approves.

Running Foreman's own project as an Assay base (a direction is already a
four-field remark) is a fair test after Assay's pilot.

**What Assay shows about Foreman today.** A task's criteria close on one
agent's word: the reviewer marks a criterion verified with free-text
evidence, and nothing records whether it ran a check or read the
developer's report. In Assay's terms that is an agent's note about its own
system with no system check behind it ("Unqualified system state";
scenario 14). That is how sprint 65's reviews approved in seconds, with
faults an independent review found afterwards. The verdict should record its
basis per criterion, and only a check that ran should count as support.

**Order:**
1. **Now:** this file, and no code. Assay's S4 is shaped with Foreman as its
   first consumer: a briefing readable by scope with a stable snapshot id, and
   bindings that accept a commit and that id. This changes Assay's roadmap,
   which is the owner's to decide.
2. **Foreman next:** the reviewer's verdict records its basis per criterion
   (with FOR-76), and the three ideas above.
3. **After Assay's S4:** briefing in and bindings out at merge, for one
   project.
4. **After Assay's S5 and S6:** findings to intake, questions to Assay, test
   runs as check runs.
5. **Waits:** a separate spec editor (`spec-editor` in the roadmap), shared
   sign-in (stage 2) and memory across projects.
