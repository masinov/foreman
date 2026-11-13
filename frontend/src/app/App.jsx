import React, { useEffect } from "react";

import { getSprint } from "../api/sprints";
import { getWorkspace } from "../api/workspace";
import { getTask } from "../api/tasks";
import { useResource } from "../api/useResource";
import { EngineMenu } from "../pages/shared/EngineMenu";
import { NotFoundPage } from "../pages/status/NotFoundPage";
import { RebuildingPage } from "../pages/status/RebuildingPage";
import { BUILT_PAGES } from "./pages";
import { ManagerPanel } from "../pages/manager/ManagerPanel";
import { useManagerOpen, useManagerTarget } from "./manager";
import { ManagerToggle } from "./ManagerToggle";
import { useRoute } from "./router";
import { useLiveData } from "./useLiveData";
import { Shell } from "./Shell";
import { SignInGate } from "./SignInGate";

/** The engine of the project a sprint or task belongs to. */
function EngineOf({ resourceKey, load }) {
  const { data } = useResource(resourceKey, load);
  return data?.project_id ? <EngineMenu projectId={data.project_id} /> : null;
}

function TopBarRight({ route, params, manager }) {
  if (route.level === "sprint") {
    return (
      <>
        <EngineOf
          resourceKey={["sprint", params.sprintId]}
          load={(client, options) => getSprint(client, params.sprintId, options)}
        />
        {manager}
      </>
    );
  }
  if (route.level === "task") {
    return (
      <>
        <EngineOf
          resourceKey={["task", params.taskId]}
          load={(client, options) => getTask(client, params.taskId, options)}
        />
        {manager}
      </>
    );
  }
  if (route.level === "project") {
    // The project page shows its engine in the page. The pages below it
    // (settings, backlog) are pages of their own, so the engine is in the bar.
    return route.name.startsWith("project-settings") || route.name === "project-backlog" ? (
      <>
        <EngineMenu projectId={params.projectId} />
        {manager}
      </>
    ) : (
      manager
    );
  }
  return null;
}

function useProjectName(projectId) {
  const { data } = useResource(["workspace"], getWorkspace, { enabled: Boolean(projectId) });
  return data?.projects.find((project) => project.id === projectId)?.name || projectId;
}

/** The application behind its sign-in: see SignInGate. */
export function App() {
  return (
    <SignInGate>
      <SignedInApp />
    </SignInGate>
  );
}

function SignedInApp() {
  const { route, params } = useRoute();
  const [managerOpen, setManagerOpen] = useManagerOpen();
  const target = useManagerTarget(route, params);
  const projectName = useProjectName(target.projectId);
  useLiveData({ projectId: target.projectId, poll: route.name === "workspace" });

  useEffect(() => {
    document.title = `${route.title} · Foreman`;
  }, [route]);

  let page;
  if (route.name === "not-found") {
    page = <NotFoundPage />;
  } else if (BUILT_PAGES[route.name]) {
    const Page = BUILT_PAGES[route.name];
    page = <Page params={params} />;
  } else {
    page = <RebuildingPage route={route} params={params} />;
  }

  return (
    <Shell
      topBarRight={
        <TopBarRight
          route={route}
          params={params}
          manager={
            target.hasManager ? (
              <ManagerToggle open={managerOpen} onToggle={() => setManagerOpen((open) => !open)} />
            ) : null
          }
        />
      }
      managerOpen={managerOpen}
      manager={
        target.hasManager ? (
          <ManagerPanel
            key={target.projectId || "no-project"}
            projectId={target.projectId}
            projectName={projectName}
            page={target.page}
            context={target.context}
            onClose={() => setManagerOpen(false)}
          />
        ) : null
      }
    >
      {/* A new key per address resets page state when the route changes. */}
      <React.Fragment key={`${route.name}:${JSON.stringify(params)}`}>{page}</React.Fragment>
    </Shell>
  );
}
