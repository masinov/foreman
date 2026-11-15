# ADR-0023: Agent sandbox, first cut

- **Status:** accepted
- **Date:** 2026-11-15
- **Sprint:** 59, slices 7 and 8

## Context

An agent step is a CLI process (Claude Code or Codex) started by the engine
as the engine's user. Until now it was started with the engine's whole
environment and the CLI's whole tool set, minus a per-role deny list:

- A role's `[agent.tools] allowed` list was read from the role file and
  never passed to the CLI.
- A reviewer was "read-only" because four tools were denied. Every other
  tool the CLI has, or gains in a later version, was available to it.
- The process inherited every variable the engine had: the dashboard token,
  a forge token, cloud credentials, an SSH agent socket.
- A check with the installed CLI on 2026-11-15 showed one more thing: an
  agent started with three tools still had the MCP connectors the operator
  had set up for their own use (documents, a drive with share and delete).

The 2026-11-10 review lists this under Phase 5 ("agents run with full
permissions as the engine's user"). This ADR records the first cut. It
narrows what an agent is handed; it does not confine the process.

## Decision

1. **A role's allowlist is the agent's whole tool set.** When
   `[agent.tools] allowed` is not empty the Claude runner passes it as
   `--tools`, and the Codex runner refuses a command or a file change the
   list does not cover. `disallowed` still applies on top. An empty list
   means "no allowlist", as before.
2. **Reviewers that read can only read.** `code_reviewer` and
   `security_reviewer` ship with `allowed = ["Read", "Grep", "Glob"]`.
   `triage_reviewer` and `frontier_reviewer` are given the change in their
   prompt and keep their deny list, which covers every reading and writing
   tool.
3. **An agent process gets a short environment.** `PATH`, `HOME`, `USER`,
   `LOGNAME`, `SHELL`, `TERM`, `COLORTERM`, `LANG`, `LANGUAGE`, `TZ`, the
   temporary-directory variables, certificate and proxy variables, and
   everything starting `LC_`, `XDG_`, `ANTHROPIC_`, `CLAUDE_`, `OPENAI_` or
   `CODEX_`. Nothing else from the engine's environment. On top of that
   come the variables the project names in `agent_env_passthrough` (a
   host-level setting, ADR-0017) and the role's `[agent.env]`.
4. **An agent gets no MCP servers the role did not name.** The Claude
   runner passes `--strict-mcp-config`. A role names servers with
   `mcp_config` under `[agent.flags]`, or opts out with
   `strict_mcp_config = false`.
5. **The manager session** is covered by the same rules; see slice 8 and
   ADR-0022.

The test command and the worktree set-up command are the operator's own and
keep the engine's environment.

## Consequences

- A developer agent can no longer reach a forge with the engine's token or
  SSH agent. It was already told not to push; now it cannot with those.
- A project whose tests, run by the developer agent, need a variable (a
  database address) names it in `agent_env_passthrough`.
- A role file of a project's own keeps working: an empty allowlist changes
  nothing for it. It does lose the operator's MCP connectors and the wider
  environment.

## Not covered

- The process still runs as the engine's user with `bypassPermissions`. A
  developer agent has a shell and can read any file that user can, including
  credential files in the home directory, and can reach the network.
- Nothing confines writes to the task's worktree.
- `HOME` is the operator's, so the CLI reads the operator's own settings,
  memory and hooks. Isolated CLI settings and a container per task are the
  later steps of Phase 5.
- Checked against the installed Claude Code CLI (2.1.325) with one real
  call: the tool list was exactly the allowlist. Codex's handling is
  covered by tests only.
