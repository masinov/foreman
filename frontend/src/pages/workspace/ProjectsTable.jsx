import React from "react";

import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Mono } from "../../ui/Mono";
import { StatusDot } from "../../ui/StatusDot";
import { Table } from "../../ui/Table";
import { formatDay, formatMoney, humanize } from "../../ui/format";
import { MilestoneText } from "../shared/milestones";
import { TaskCounts } from "../shared/TaskCounts";
import { engineWords } from "../shared/words";

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

function EngineCell({ engine }) {
  const { tone, word } = engineWords(engine?.state);
  return (
    <div className="cell-stack">
      <StatusDot tone={tone}>{word}</StatusDot>
      {engine?.task_id ? (
        <span className="quiet">
          <Mono quiet>{engine.task_key || engine.task_title}</Mono>
          {engine.step ? `, ${humanize(engine.step).toLowerCase()}` : ""}
        </span>
      ) : null}
    </div>
  );
}

function SprintCell({ sprint }) {
  if (!sprint) {
    return <span className="quiet">None</span>;
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
      <MilestoneText milestone={milestone} short />
      <span className="quiet">{formatDay(milestone.at)}</span>
    </div>
  );
}

const COLUMNS = [
  { key: "project", header: "Project, location, branch", className: "projects__project", render: (p) => <ProjectCell project={p} /> },
  { key: "engine", header: "Engine", className: "projects__engine", render: (p) => <EngineCell engine={p.engine} /> },
  { key: "sprint", header: "Active sprint", className: "projects__sprint", render: (p) => <SprintCell sprint={p.active_sprint} /> },
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
    render: (p) => (p.active_sprint ? <Mono>{formatMoney(p.active_sprint.spend_usd)}</Mono> : null),
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
        No projects yet. A project added from the command line (foreman init) appears here.
      </p>
    );
  }
  return <Table caption="Projects" columns={COLUMNS} rows={projects} />;
}
