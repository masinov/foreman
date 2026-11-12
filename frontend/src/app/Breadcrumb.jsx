import React from "react";

import { getProject } from "../api/projects";
import { getSprint } from "../api/sprints";
import { getTask } from "../api/tasks";
import { useResource } from "../api/useResource";
import { paths } from "./paths";
import { Link, useRoute } from "./router";

function useLabel(key, load, pick, fallback) {
  const { data } = useResource(key, load, { enabled: Boolean(key[1]) });
  return (data && pick(data)) || fallback;
}

function ProjectCrumb({ projectId }) {
  return useLabel(["project", projectId], (client, options) => getProject(client, projectId, options), (p) => p.name, projectId);
}

function SprintCrumb({ sprintId }) {
  return useLabel(["sprint", sprintId], (client, options) => getSprint(client, sprintId, options), (s) => s.title, sprintId);
}

function TaskCrumb({ taskId }) {
  return useLabel(["task", taskId], (client, options) => getTask(client, taskId, options), (t) => t.task_key || t.title, taskId);
}

/** The levels of the current route: Workspace / Project / Sprint / Task. */
export function crumbsFor(route, params) {
  const workspace = { key: "workspace", href: paths.workspace(), label: "Workspace" };
  switch (route.level) {
    case "project": {
      const crumbs = [
        workspace,
        { key: "project", href: paths.project(params.projectId), label: <ProjectCrumb projectId={params.projectId} /> },
      ];
      if (route.name.startsWith("project-settings")) {
        crumbs.push({ key: "settings", href: paths.projectSettings(params.projectId), label: "Settings" });
      }
      return crumbs;
    }
    case "sprint":
      return [workspace, { key: "sprint", href: paths.sprint(params.sprintId), label: <SprintCrumb sprintId={params.sprintId} /> }];
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
              {last || !crumb.href ? (
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
