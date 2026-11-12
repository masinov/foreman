// API answers for project settings, on top of the workspace's.
import { workspaceRoutes } from "./workspaceFixture";

export const SETTINGS_URL = "GET /api/v1/projects/foreman/settings";
export const SAVE_URL = "PATCH /api/v1/projects/foreman/settings";
export const WORKFLOW_URL = "GET /api/v1/projects/foreman/workflow";
export const WORKFLOWS_URL = "GET /api/v1/workflows";

export const EFFECTIVE = {
  triage: "human",
  plan_approval: "human",
  merge_approval: "auto",
  policy_rules: {},
  task_selection_mode: "directed",
  max_autonomous_tasks: 5,
  cost_limit_per_task_usd: 0,
  cost_limit_per_sprint_usd: 12.5,
  time_limit_per_task_ms: 0,
  max_step_visits: 5,
  max_live_worktrees: 4,
  default_model: "",
  meta_agent_model: "claude-opus-5-5",
  test_command: "./venv/bin/python -m unittest",
  test_timeout_seconds: 1800,
  notification: "attention",
  event_retention_days: null,
  run_retention_days: 30,
  prompt_retention_days: null,
  worktree_root: "",
  worktree_setup_command: "ln -s ../node_modules frontend/node_modules",
  worktree_link_paths: ["venv"],
  context_dir: "",
  judge_base_url: "",
  judge_api_key_env: "",
};

export function settingsPayload(effective = {}) {
  return {
    project_id: "foreman",
    workflow_id: "development",
    default_branch: "main",
    spec_path: "",
    autonomy_level: "supervised",
    settings: {},
    effective: { ...EFFECTIVE, ...effective },
    host_level_settings: [
      "context_dir",
      "judge_api_key_env",
      "judge_base_url",
      "test_command",
      "worktree_link_paths",
      "worktree_root",
      "worktree_setup_command",
    ],
  };
}

const DEVELOPER = {
  id: "developer",
  name: "Developer",
  description: "Writes code, tests, and documentation for assigned tasks",
  backend: "claude_code",
  model: "",
};
const REVIEWER = {
  id: "code_reviewer",
  name: "Code Reviewer",
  description: "Reviews completed work and returns APPROVE, DENY, or STEER",
  backend: "claude_code",
  model: "claude-sonnet-5-5",
};

const edge = (from, outcome, to, carry = false) => ({
  from,
  trigger: `completion:${outcome}`,
  outcome,
  to,
  carry_output: carry,
});

export const DEVELOPMENT = {
  id: "development",
  name: "Standard Development",
  methodology: "development",
  source_path: "/srv/foreman/foreman/data/workflows/development.toml",
  steps: [
    { id: "develop", role: "developer", policy: null },
    { id: "test", role: "_builtin:run_tests", policy: null },
    { id: "review", role: "code_reviewer", policy: null },
    { id: "merge_approval", role: "_builtin:human_gate", policy: "merge_approval" },
    { id: "merge", role: "_builtin:merge", policy: null },
    { id: "done", role: "_builtin:mark_done", policy: null },
  ],
  transitions: [
    edge("develop", "done", "test"),
    edge("test", "success", "review"),
    edge("test", "failure", "develop", true),
    edge("review", "approve", "merge_approval"),
    edge("review", "deny", "develop", true),
    edge("review", "steer", "develop", true),
    edge("merge_approval", "approve", "merge"),
    edge("merge_approval", "deny", "develop", true),
    edge("merge_approval", "steer", "develop", true),
    edge("merge", "success", "done"),
    edge("merge", "conflict", "develop", true),
    edge("merge", "failure", "develop", true),
  ],
  roles: [DEVELOPER, REVIEWER],
  requirements: [
    { id: "tests", kind: "fact", text: "Tests pass at the commit being merged", steps: ["test"] },
    { id: "code-review", kind: "claim", text: "Code review approves that same commit", steps: ["review"] },
    { id: "acceptance-criteria", kind: "claim", text: "Acceptance criteria marked met", steps: ["review"] },
  ],
  requirements_enforced: true,
};

/** A different workflow: a plan gate, no tests, and one reviewer who may only approve or deny. */
export const LIGHT = {
  id: "light",
  name: "Light Review",
  methodology: "development",
  source_path: "/srv/foreman/foreman/data/workflows/light.toml",
  steps: [
    { id: "draft", role: "developer", policy: null },
    { id: "plan_approval", role: "_builtin:human_gate", policy: "plan_approval" },
    { id: "ship", role: "_builtin:merge", policy: null },
  ],
  transitions: [
    edge("draft", "done", "plan_approval"),
    edge("plan_approval", "approve", "ship"),
    edge("plan_approval", "deny", "draft"),
  ],
  roles: [DEVELOPER],
  requirements: [],
  requirements_enforced: true,
};

export function settingsRoutes({ effective, workflow = DEVELOPMENT, workflows = [DEVELOPMENT, LIGHT] } = {}) {
  return {
    ...workspaceRoutes(),
    [SETTINGS_URL]: settingsPayload(effective),
    [WORKFLOW_URL]: workflow,
    [WORKFLOWS_URL]: { workflows },
  };
}
