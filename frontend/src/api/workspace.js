import { listProjectGates } from "./gates";
import { getProject, listProjects } from "./projects";
import { listProjectSprints, listSprintTasks } from "./sprints";
import { getTask } from "./tasks";

/**
 * The workspace overview: every project with its engine and active sprint,
 * and one "Needs you" list across all of them.
 *
 * Built from the per-resource endpoints that exist today. A later slice adds
 * one workspace endpoint; when it lands, this module calls it instead and the
 * page does not change.
 */

export const NEEDS_YOU_KINDS = {
  approval: "approval",
  unblock: "unblock",
  accept: "accept",
  sprintOrder: "sprint_order",
};

const KIND_ORDER = [
  NEEDS_YOU_KINDS.approval,
  NEEDS_YOU_KINDS.unblock,
  NEEDS_YOU_KINDS.accept,
  NEEDS_YOU_KINDS.sprintOrder,
];

function sprintMayHoldDecisions(sprint) {
  const counts = sprint.task_counts || {};
  return (counts.blocked || 0) + (counts.triage || 0) > 0;
}

function taskItem(project, sprint, task, detail) {
  const base = {
    projectId: project.id,
    projectName: project.name,
    sprintId: sprint.id,
    taskId: task.id,
    taskKey: task.task_key || null,
    title: task.title,
  };
  if (task.awaiting_human_gate) {
    return {
      ...base,
      id: `task:${task.id}`,
      kind: NEEDS_YOU_KINDS.approval,
      step: task.workflow_current_step || null,
      evidence: detail?.completion_evidence ?? null,
    };
  }
  if (task.blocked_kind === "engine") {
    return {
      ...base,
      id: `task:${task.id}`,
      kind: NEEDS_YOU_KINDS.unblock,
      reason: task.blocked_reason || null,
    };
  }
  if (task.status === "triage") {
    return {
      ...base,
      id: `task:${task.id}`,
      kind: NEEDS_YOU_KINDS.accept,
      source: task.source ?? null,
    };
  }
  return null;
}

function gateItem(project, gate) {
  return {
    id: `gate:${gate.id}`,
    kind: NEEDS_YOU_KINDS.sprintOrder,
    projectId: project.id,
    projectName: project.name,
    gateId: gate.id,
    title: gate.conflict_description,
    reason: gate.suggested_reason || null,
    raisedAt: gate.raised_at || null,
  };
}

async function loadProjectOverview(client, summary, options) {
  const [detail, sprints, gates] = await Promise.all([
    getProject(client, summary.id, options),
    listProjectSprints(client, summary.id, options),
    listProjectGates(client, summary.id, { ...options, status: "pending" }),
  ]);

  const scanned = sprints.filter(sprintMayHoldDecisions);
  const taskLists = await Promise.all(
    scanned.map((sprint) => listSprintTasks(client, sprint.id, options)),
  );

  const candidates = [];
  scanned.forEach((sprint, index) => {
    for (const task of taskLists[index]) {
      if (task.awaiting_human_gate || task.blocked_kind === "engine" || task.status === "triage") {
        candidates.push({ sprint, task });
      }
    }
  });

  // What was checked lives on the task detail (its completion evidence).
  const details = await Promise.all(
    candidates.map(({ task }) =>
      task.awaiting_human_gate ? getTask(client, task.id, options) : Promise.resolve(null),
    ),
  );

  const needsYou = [
    ...candidates
      .map(({ sprint, task }, index) => taskItem(summary, sprint, task, details[index]))
      .filter(Boolean),
    ...gates.map((gate) => gateItem(summary, gate)),
  ];

  const activeSprint = sprints.find((sprint) => sprint.status === "active") ?? null;
  const plannedSprints = sprints.filter((sprint) => sprint.status === "planned").length;

  return {
    id: summary.id,
    name: summary.name,
    repoPath: detail.repo_path ?? null,
    defaultBranch: detail.default_branch ?? null,
    engine: summary.engine ?? null,
    activeSprint: activeSprint
      ? {
          id: activeSprint.id,
          title: activeSprint.title,
          taskCounts: activeSprint.task_counts || {},
          costUsd: activeSprint.totals?.total_cost_usd ?? 0,
        }
      : null,
    plannedSprints,
    needsYouCount: needsYou.length,
    needsYou,
  };
}

function byKind(left, right) {
  return KIND_ORDER.indexOf(left.kind) - KIND_ORDER.indexOf(right.kind);
}

export async function loadWorkspace(client, options) {
  const summaries = await listProjects(client, options);
  const projects = await Promise.all(
    summaries.map((summary) => loadProjectOverview(client, summary, options)),
  );
  const needsYou = projects.flatMap((project) => project.needsYou).sort(byKind);
  return {
    projects: projects.map(({ needsYou: _items, ...project }) => project),
    needsYou,
  };
}
