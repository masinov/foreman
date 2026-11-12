// API answers for workspace settings and the user menu, on top of the workspace's.
import { DEVELOPMENT, LIGHT } from "./settingsFixture";
import { workspaceRoutes } from "./workspaceFixture";

export const ROLES = [
  {
    id: "developer",
    name: "Developer",
    description: "Writes code, tests, and documentation for assigned tasks",
    backend: "claude_code",
    model: "",
    permission_mode: "bypassPermissions",
    session_persistence: true,
    timeout_minutes: 60,
    max_cost_usd: 5,
    source_path: "/srv/foreman/foreman/data/roles/developer.toml",
  },
  {
    id: "code_reviewer",
    name: "Code Reviewer",
    description: "Reviews completed work and returns APPROVE, DENY, or STEER",
    backend: "claude_code",
    model: "claude-sonnet-5-5",
    permission_mode: "plan",
    session_persistence: false,
    timeout_minutes: 30,
    max_cost_usd: 0,
    source_path: "/srv/foreman/foreman/data/roles/code_reviewer.toml",
  },
];

export const TOKEN = {
  id: "tok-1",
  project_id: "foreman",
  project_name: "Foreman",
  name: "pagerduty",
  scopes: ["intake"],
  created_by: "human",
  created_at: "2026-11-01T09:00:00Z",
  last_used_at: "2026-11-10T09:30:00Z",
  revoked_at: null,
  active: true,
};

export const REVOKED_TOKEN = {
  ...TOKEN,
  id: "tok-0",
  name: "old-ci",
  last_used_at: null,
  revoked_at: "2026-11-05T09:00:00Z",
  active: false,
};

export const CHANNEL = {
  id: "dst-1",
  project_id: "foreman",
  project_name: "Foreman",
  name: "ops-channel",
  kind: "webhook",
  target: "https://hooks.example.test/ops",
  signed: true,
  enabled: true,
  created_at: "2026-11-02T09:00:00Z",
};

export const RUNNERS = [
  {
    id: "claude_code",
    name: "Claude Code",
    executable: "claude",
    found: true,
    path: "/usr/local/bin/claude",
    models: ["claude-sonnet-5-5"],
    uses_default: true,
  },
  { id: "codex", name: "Codex", executable: "codex", found: false, path: null, models: [], uses_default: false },
];

export const MACHINE = {
  database_path: "/srv/foreman/.foreman.db",
  version: "0.9.1",
  address: "http://localhost:8080",
};

/** Workspace settings with everything configured; pass overrides to change a part. */
export function accessRoutes({ tokens = [TOKEN, REVOKED_TOKEN], channels = [CHANNEL], session } = {}) {
  const routes = {
    ...workspaceRoutes(),
    "GET /api/v1/workflows": { workflows: [DEVELOPMENT, LIGHT] },
    "GET /api/v1/roles": { roles: ROLES },
    "GET /api/v1/tokens": { tokens, scopes: ["intake"] },
    "GET /api/v1/notification-channels": { channels, kinds: ["webhook"] },
    "GET /api/v1/runners": { runners: RUNNERS },
    "GET /api/v1/machine": MACHINE,
  };
  if (session) routes["GET /api/v1/session"] = session;
  return routes;
}
