import React from "react";

import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Mono } from "../../ui/Mono";
import { Table } from "../../ui/Table";
import { formatDayTime } from "../../ui/format";
import { Spend } from "../../ui/Spend";
import { milestoneSentence } from "../shared/milestones";
import { TaskCounts } from "../shared/TaskCounts";
import { WorkStatus } from "../shared/WorkStatus";

function ProjectCell({ project }) {
  const location = [project.repo_path, project.default_branch].filter(Boolean).join(" · ");
  return (
    <div className="cell-stack">
      <Link className="row-link row-link--strong" href={paths.project(project.id)}>
        {project.name}
      </Link>
      {location ? <Mono quiet>{location}</Mono> : null}
    </div>
  );
}


function plannedWording(count) {
  return count > 0 ? `${count} planned` : "nothing planned";
}

function SprintCell({ sprint, planned }) {
  if (!sprint) {
    return (
      <div className="cell-stack">
        <span className="quiet">None</span>
        <span className="quiet">{plannedWording(planned)}</span>
      </div>
    );
  }
  return (
    <div className="cell-stack">
      <Link className="row-link" href={paths.sprint(sprint.id)}>
        {sprint.title}
      </Link>
      <span className="quiet">
        <TaskCounts counts={sprint.task_counts} />
      </span>
    </div>
  );
}

function LastChangeCell({ milestone }) {
  if (!milestone) return <span className="quiet">nothing yet</span>;
  return (
    <div className="cell-stack">
      {milestone.sprint_id ? (
        <Link className="row-link" href={paths.sprint(milestone.sprint_id)}>
          {milestoneSentence(milestone)}
        </Link>
      ) : (
        <span>{milestoneSentence(milestone)}</span>
      )}
      <span className="quiet">{formatDayTime(milestone.at)}</span>
    </div>
  );
}

const COLUMNS = [
  { key: "project", header: "Project, location, branch", className: "projects__project", render: (p) => <ProjectCell project={p} /> },
  // What the project's work is doing now: its active sprint's status line (ADR-0043).
  { key: "work", header: "Work", className: "projects__work", render: (p) => <WorkStatus work={p.work} /> },
  { key: "sprint", header: "Active sprint", className: "projects__sprint", render: (p) => <SprintCell sprint={p.active_sprint} planned={p.planned_sprints} /> },
  {
    key: "needs-you",
    header: "Needs you",
    numeric: true,
    render: (p) => <span className={p.needs_you > 0 ? "attention" : "quiet"}>{p.needs_you}</span>,
  },
  {
    key: "backlog",
    header: "Backlog",
    numeric: true,
    render: (p) => (
      <Link className="row-link" href={paths.projectBacklog(p.id)} aria-label={`${p.name} backlog, ${p.backlog}`}>
        {p.backlog}
      </Link>
    ),
  },
  {
    key: "spend",
    header: "Sprint spend",
    numeric: true,
    render: (p) => (p.active_sprint ? <Spend amount={p.active_sprint.spend_usd} where="row" /> : null),
  },
  { key: "last", header: "Last change", className: "projects__last", render: (p) => <LastChangeCell milestone={p.latest_milestone} /> },
];

export function ProjectsTable({ projects, placeholder }) {
  if (placeholder) {
    return <Table caption="Projects" columns={COLUMNS} placeholderRows={3} />;
  }
  if (!projects) return null;
  if (projects.length === 0) {
    return (
      <p className="empty">
        No projects yet. Add one to give Foreman a repository to work in.
      </p>
    );
  }
  return <Table caption="Projects" columns={COLUMNS} rows={projects} />;
}
