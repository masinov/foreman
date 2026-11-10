# ADR-0017: Host-Level Settings Are Operator-Only

- Status: accepted
- Date: 2026-11-10
- Deciders: engine team

## Context

Project settings were one bag, all writable through
`PATCH /api/projects/{id}/settings`. Some of them decide what runs on the
host or where Foreman writes and sends data: `test_command` and
`worktree_setup_command` are run through a shell by the engine,
`worktree_root` and `context_dir` choose directories Foreman creates and
deletes in, `worktree_link_paths` links operator paths into agent worktrees,
and `judge_base_url` with `judge_api_key_env` sends a diff and a named
environment variable to a chosen URL. `PATCH /api/roles/{id}` could likewise
change a role's `backend` and `permission_mode` for every project.

So every dashboard caller could execute code as the engine's user. ADR-0016
closed the browser route to the API; this closes the capability itself.
The 2026-11-10 review also reproduced worktree prune deleting an unrelated
directory after `worktree_root` was pointed at its parent.

## Decision

1. `foreman/settings.py` names `HOST_LEVEL_SETTINGS`. The dashboard service
   refuses any update that would change one of them (403, naming the key and
   the terminal command). A client that sends back the values it read is not
   changing anything and is accepted, so the Settings panel's whole-payload
   save keeps working. The settings response lists the keys so the UI shows
   them read-only.
2. Role `backend` and `permission_mode` are refused over HTTP the same way.
   `model`, timeout and cost ceiling stay editable. The role file is written
   to a temporary file, validated, then swapped in.
3. The operator path is the terminal: `foreman config <project> --set
   key=value` for settings, the TOML file for roles. Whoever can run those
   already has a shell as that user, so nothing is granted.
4. Worktree removal only ever deletes a git worktree of the project's
   repository: one git has registered, or a directory whose `.git` file
   points into that repository's worktree admin area. Any other directory
   under the root is listed with `owned: false` and kept. The root itself is
   never removed.
5. Intake accepts only `http` and `https` source URLs.

## Consequences

- The dashboard cannot be used to set a test command for a new project;
  `foreman init` and `foreman config` do that. When login and roles exist
  (finish plan, Phase 5) an administrator role may get these back.
- Registering a project by repository path stays an API action, confined by
  `FOREMAN_DASHBOARD_REPO_ROOTS` when set. Making that allowlist mandatory
  off loopback is left for the identity work.
- A directory left under the worktree root by an older layout is no longer
  cleaned up automatically.
