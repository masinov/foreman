# Running unattended

What has been done to let the engine run without a person watching, and what
is still true of the host. Moved from `docs/STATUS.md` on 2026-11-26.

Sprint 55 closed the six host and money risks the 2026-11-10 review
reproduced: browser routes into the API (ADR-0016), API control over shell
commands, paths and role permissions (ADR-0017), unbounded per-run spend,
agents outliving the engine, the lease loss that re-ran the developer, and
approve/deny executing outside the engine lock (ADR-0011 amendment). None of
this was exercised by one real engine run (FOR-13, 2026-11-10: develop, test,
review, human gate, deferred approval, merge). Sprint 59 narrowed what an agent is handed (ADR-0023): a role's tool
allowlist is passed to the CLI, the reading reviewers have three tools, and
an agent process no longer gets the engine's environment or the operator's
MCP connectors. Still true: the process runs as the engine's user with a
shell and the network (a container per task is later in Phase 5), and there
is no login.
