import React from "react";

import { getSprint } from "../api/sprints";
import { getTask } from "../api/tasks";
import { useResource } from "../api/useResource";
import { getWorkspace } from "../api/workspace";
import { Menu } from "../ui/Menu";
import { paths } from "./paths";
import { Link, useRoute } from "./router";

// A crumb shows a name or nothing. An id standing in for a name flashes on
// screen and then changes, which reads as a glitch.
function useLabel(key, load, pick) {
  const { data } = useResource(key, load, { enabled: Boolean(key[1]) });
  return (data && pick(data)) || "";
}

function useProjects() {
  const { data } = useResource(["workspace"], getWorkspace);
  return data ? data.projects : null;
}

function ProjectCrumb({ projectId }) {
  const projects = useProjects();
  return projects?.find((project) => project.id === projectId)?.name || "";
}

/**
 * The project in the breadcrumb, as a switcher: a menu of every project with
 * what waits for a person in each, going to the chosen project.
 */
function ProjectSwitcher({ projectId }) {
  const projects = useProjects();
  const project = projects?.find((entry) => entry.id === projectId);
  const name = project?.name || "";
  if (!projects || projects.length === 0) {
    return (
      <span className="breadcrumb__current" aria-current="page">
        {name}
      </span>
    );
  }
  return (
    <Menu
      label="Projects"
      triggerClassName="breadcrumb__current breadcrumb__switcher"
      aria-current="page"
      trigger={
        <>
          <span>{name}</span>
          {project?.needs_you > 0 ? (
            <span className="breadcrumb__count">
              {project.needs_you}
              <span className="visually-hidden"> need you</span>
            </span>
          ) : null}
        </>
      }
      items={projects.map((entry) => ({
        key: entry.id,
        label: entry.name,
        detail: entry.needs_you > 0 ? entry.needs_you : null,
        href: paths.project(entry.id),
        current: entry.id === projectId,
      }))}
    />
  );
}

function SprintCrumb({ sprintId }) {
  return useLabel(["sprint", sprintId], (client, options) => getSprint(client, sprintId, options), (s) => s.title);
}

/**
 * The project above a sprint: a link back to it with what waits for a person
 * there. Until the sprint says which project it belongs to, nothing shows.
 */
function SprintProjectCrumb({ sprintId }) {
  const { data: sprint } = useResource(["sprint", sprintId], (client, options) => getSprint(client, sprintId, options));
  if (!sprint?.project_id) return null;
  return <ProjectLink projectId={sprint.project_id} />;
}

/** A link to a project with what waits for a person there. */
function ProjectLink({ projectId }) {
  const projects = useProjects();
  const project = projects?.find((entry) => entry.id === projectId);
  return (
    <Link className="breadcrumb__link breadcrumb__project" href={paths.project(projectId)}>
      <span>{project?.name || ""}</span>
      {project?.needs_you > 0 ? (
        <span className="breadcrumb__count">
          {project.needs_you}
          <span className="visually-hidden"> need you</span>
        </span>
      ) : null}
    </Link>
  );
}

function TaskCrumb({ taskId }) {
  return useLabel(["task", taskId], (client, options) => getTask(client, taskId, options), (t) => t.task_key || t.title);
}

/**
 * The project and the sprint above a task, as links. A task in the backlog
 * has the project's Backlog where a sprint would be. Until the task says
 * where it belongs, nothing shows.
 */
function TaskParentCrumb({ taskId, level }) {
  const { data: task } = useResource(["task", taskId], (client, options) => getTask(client, taskId, options));
  if (!task?.project_id) return null;
  if (level === "project") return <ProjectLink projectId={task.project_id} />;
  if (task.in_backlog) {
    return (
      <Link className="breadcrumb__link" href={paths.projectBacklog(task.project_id)}>
        Backlog
      </Link>
    );
  }
  if (!task.sprint_id) return null;
  return (
    <Link className="breadcrumb__link" href={paths.sprint(task.sprint_id)}>
      <SprintCrumb sprintId={task.sprint_id} />
    </Link>
  );
}

/**
 * The levels of the current route, below the workspace. The wordmark beside
 * the breadcrumb is the one way to the workspace; there is no "Workspace"
 * step and no "All projects" entry, each of which would be a second link to
 * the same page. On the workspace page itself the breadcrumb is empty.
 */
export function crumbsFor(route, params) {
  switch (route.level) {
    case "project": {
      if (route.name.startsWith("project-settings")) {
        return [
          { key: "project", href: paths.project(params.projectId), label: <ProjectCrumb projectId={params.projectId} /> },
          { key: "settings", href: paths.projectSettings(params.projectId), label: "Settings" },
        ];
      }
      return [{ key: "project", custom: <ProjectSwitcher projectId={params.projectId} /> }];
    }
    case "sprint":
      return [
        { key: "project", custom: <SprintProjectCrumb sprintId={params.sprintId} /> },
        { key: "sprint", href: paths.sprint(params.sprintId), label: <SprintCrumb sprintId={params.sprintId} /> },
      ];
    case "task":
      return [
        { key: "project", custom: <TaskParentCrumb taskId={params.taskId} level="project" /> },
        { key: "sprint", custom: <TaskParentCrumb taskId={params.taskId} level="sprint" /> },
        { key: "task", href: paths.task(params.taskId), label: <TaskCrumb taskId={params.taskId} /> },
      ];
    default:
      if (route.name === "workspace-settings") {
        return [{ key: "settings", href: paths.workspaceSettings(), label: "Workspace settings" }];
      }
      if (route.name === "not-found") {
        return [{ key: "not-found", href: null, label: "Not found" }];
      }
      return [];
  }
}

export function Breadcrumb() {
  const { route, params } = useRoute();
  const crumbs = crumbsFor(route, params);
  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      <ol className="breadcrumb__list">
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          return (
            <li key={crumb.key} className="breadcrumb__item">
              {crumb.custom ? (
                crumb.custom
              ) : last || !crumb.href ? (
                <span className="breadcrumb__current" aria-current={last ? "page" : undefined}>
                  {crumb.label}
                </span>
              ) : (
                <Link className="breadcrumb__link" href={crumb.href}>
                  {crumb.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
