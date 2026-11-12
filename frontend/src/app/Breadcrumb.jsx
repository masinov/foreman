import React from "react";

import { getSprint } from "../api/sprints";
import { getTask } from "../api/tasks";
import { useResource } from "../api/useResource";
import { getWorkspace } from "../api/workspace";
import { Menu } from "../ui/Menu";
import { paths } from "./paths";
import { Link, useRoute } from "./router";

function useLabel(key, load, pick, fallback) {
  const { data } = useResource(key, load, { enabled: Boolean(key[1]) });
  return (data && pick(data)) || fallback;
}

function useProjects() {
  const { data } = useResource(["workspace"], getWorkspace);
  return data ? data.projects : null;
}

function ProjectCrumb({ projectId }) {
  const projects = useProjects();
  return projects?.find((project) => project.id === projectId)?.name || projectId;
}

/**
 * The project in the breadcrumb, as a switcher: a menu of every project with
 * what waits for a person in each, going to the chosen project.
 */
function ProjectSwitcher({ projectId }) {
  const projects = useProjects();
  const project = projects?.find((entry) => entry.id === projectId);
  const name = project?.name || projectId;
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
  return useLabel(["sprint", sprintId], (client, options) => getSprint(client, sprintId, options), (s) => s.title, sprintId);
}

/**
 * The project above a sprint: a link back to it with what waits for a person
 * there. Until the sprint says which project it belongs to, nothing shows.
 */
function SprintProjectCrumb({ sprintId }) {
  const { data: sprint } = useResource(["sprint", sprintId], (client, options) => getSprint(client, sprintId, options));
  const projects = useProjects();
  if (!sprint?.project_id) return null;
  const project = projects?.find((entry) => entry.id === sprint.project_id);
  return (
    <Link className="breadcrumb__link breadcrumb__project" href={paths.project(sprint.project_id)}>
      <span>{project?.name || sprint.project_id}</span>
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
  return useLabel(["task", taskId], (client, options) => getTask(client, taskId, options), (t) => t.task_key || t.title, taskId);
}

/** The levels of the current route: Workspace / Project / Sprint / Task. */
export function crumbsFor(route, params) {
  const workspace = { key: "workspace", href: paths.workspace(), label: "Workspace" };
  switch (route.level) {
    case "project": {
      if (route.name.startsWith("project-settings")) {
        return [
          workspace,
          { key: "project", href: paths.project(params.projectId), label: <ProjectCrumb projectId={params.projectId} /> },
          { key: "settings", href: paths.projectSettings(params.projectId), label: "Settings" },
        ];
      }
      return [workspace, { key: "project", custom: <ProjectSwitcher projectId={params.projectId} /> }];
    }
    case "sprint":
      return [
        workspace,
        { key: "project", custom: <SprintProjectCrumb sprintId={params.sprintId} /> },
        { key: "sprint", href: paths.sprint(params.sprintId), label: <SprintCrumb sprintId={params.sprintId} /> },
      ];
    case "task":
      return [workspace, { key: "task", href: paths.task(params.taskId), label: <TaskCrumb taskId={params.taskId} /> }];
    default:
      if (route.name === "workspace-settings") {
        return [workspace, { key: "settings", href: paths.workspaceSettings(), label: "Settings" }];
      }
      if (route.name === "not-found") {
        return [workspace, { key: "not-found", href: null, label: "Not found" }];
      }
      return [workspace];
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
