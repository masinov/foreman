Agents no longer get the operator's Claude Code memory

- Claude Code agents start with auto-memory off (`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`), so a person's private notes for the repository do not reach them.
- An agent still gets its worktree's own `CLAUDE.md` and `AGENTS.md`; the MANUAL says what an agent is given.
