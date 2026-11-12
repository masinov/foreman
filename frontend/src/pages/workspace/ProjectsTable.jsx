import React from "react";

import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Mono } from "../../ui/Mono";
import { StatusDot } from "../../ui/StatusDot";
import { Table } from "../../ui/Table";
import { formatMoney, humanize } from "../../ui/format";

const ENGINE_WORDS = {
  resident: { tone: "running", word: "Running" },
  paused: { tone: "idle", word: "Paused" },
  stopped: { tone: "idle", word: "Not running" },
};

// The order a person reads a sprint in: what is moving, what is stuck, what
// is waiting, what is finished.
const COUNT_WORDS = [
  ["in_progress", "in progress"],
  ["blocked", "blocked"],
  ["todo", "to do"],
  ["triage", "filed"],
  ["done", "done"],
];

export function describeTaskCounts(counts) {
  const parts = COUNT_WORDS.filter(([status]) => (counts?.[status] || 0) > 0).map(
    ([status, word]) => `${counts[status]} ${word}`,
  );
  return parts.length ? parts.join(" · ") : "no tasks";
}

function ProjectCell({ project }) {
  const location = [project.repoPath, project.defaultBranch].filter(Boolean).join(" · ");
  return (
    <div className="cell-stack">
      <Link className="row-link row-link--strong" href={paths.project(project.id)}>
        {project.name}
      </Link>
      {location ? <Mono quiet>{location}</Mono> : null}
    </div>
  );
}

function EngineCell({ engine }) {
  const state = ENGINE_WORDS[engine?.state] ?? ENGINE_WORDS.stopped;
  const task = engine?.current_task;
  return (
    <div className="cell-stack">
      <StatusDot tone={state.tone}>{state.word}</StatusDot>
      {task ? (
        <span className="quiet">
          <Mono quiet>{task.task_key || task.title}</Mono>
          {task.workflow_current_step ? `, ${humanize(task.workflow_current_step).toLowerCase()}` : ""}
        </span>
      ) : (
        <span className="quiet">working on nothing</span>
      )}
    </div>
  );
}

function SprintCell({ project }) {
  const sprint = project.activeSprint;
  if (!sprint) {
    return (
      <div className="cell-stack">
        <span>None</span>
        <span className="quiet">
          {project.plannedSprints > 0 ? `${project.plannedSprints} planned` : "nothing planned"}
        </span>
      </div>
    );
  }
  return (
    <div className="cell-stack">
      <Link className="row-link" href={paths.sprint(sprint.id)}>
        {sprint.title}
      </Link>
      <span className="quiet">{describeTaskCounts(sprint.taskCounts)}</span>
    </div>
  );
}

const COLUMNS = [
  { key: "project", header: "Project, location, branch", className: "projects__project", render: (p) => <ProjectCell project={p} /> },
  { key: "engine", header: "Engine", className: "projects__engine", render: (p) => <EngineCell engine={p.engine} /> },
  { key: "sprint", header: "Active sprint", className: "projects__sprint", render: (p) => <SprintCell project={p} /> },
  {
    key: "needs-you",
    header: "Needs you",
    className: "projects__number",
    render: (p) => <span className={p.needsYouCount > 0 ? "attention" : "quiet"}>{p.needsYouCount}</span>,
  },
  {
    key: "spend",
    header: "Sprint spend",
    className: "projects__number",
    render: (p) => (p.activeSprint ? <Mono>{formatMoney(p.activeSprint.costUsd)}</Mono> : null),
  },
];

export function ProjectsTable({ projects, placeholder }) {
  if (placeholder) {
    return <Table caption="Projects" columns={COLUMNS} placeholderRows={3} />;
  }
  if (!projects) return null;
  if (projects.length === 0) {
    return (
      <p className="empty">
        No projects yet. A project added from the previous dashboard or the command line appears here.
      </p>
    );
  }
  return <Table caption="Projects" columns={COLUMNS} rows={projects} />;
}
