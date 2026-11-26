# Which models and harnesses run which work, configured by the user

- Date: owner, 2026-11-25
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.

**Which models and harnesses run which work, configured by the user
(owner, 2026-11-25).** One ladder per role ("cheap, then strong") is too
simple. A user should be able to define combinations they have found
work for kinds of task, for example Kimi for frontend work, DeepSeek for
backend work, Fable or Astra for hard mathematics, with their own tiers
and handoffs. "Let the user play with it and configure what they
empirically determine works best for their workflows", rather than a
fixed "hard or easy", "long or short" tier. For the future.
- **A runner profile, not a model.** Harness (Claude Code, Codex, later
  others), model, endpoint and its settings (an Anthropic-compatible
  endpoint through `[agent.env]` already works) and effort. A ladder is
  an ordered list of profiles.
- **Which ladder, chosen by the same fixed facts as routes** (ADR-0041):
  a label the project defines, the task type, a changed path group
  (known after develop; before it, from the planner's expected files).
  First matching rule wins, and a rule without facts is the default. No
  free expressions, so every choice can be explained: "Develop runs on
  Kimi: label frontend".
- **A handoff across harnesses cannot resume a session.** The next rung
  starts fresh from the step's declared inputs: the task, the records
  (the report, the findings) and the change so far (ADR-0041 section 5).
  Step records are what make this possible.
- **Each profile must pass what Foreman relies on:** records, the
  completion marker, commands without standard input, the sandbox, cost
  reporting. A profile that cannot is refused when it is saved.
- **Empirical by design:** `foreman outcomes` per rule and profile (cost,
  send-backs, time, failures), so a user sees what works. Later Foreman
  could suggest a change to a rule from those numbers.
- **Per provider:** keys passed to the agent by name, quotas and prices
  tracked separately.
- Builds on today's decision on moving up after failures (see
  [the size label goes](the-size-label-goes-and-a-step-moves-up-after-failures.md)), which works the same with one ladder.
