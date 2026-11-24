import React, { useEffect } from "react";

import { getSprint } from "../api/sprints";
import { getWorkspace } from "../api/workspace";
import { getTask } from "../api/tasks";
import { useResource } from "../api/useResource";
import { EngineMenu } from "../pages/shared/EngineMenu";
import { NotFoundPage } from "../pages/status/NotFoundPage";
import { RebuildingPage } from "../pages/status/RebuildingPage";
import { BUILT_PAGES, pageKey } from "./pages";
import { ManagerPanel } from "../pages/manager/ManagerPanel";
import { AgentPanel } from "../pages/task/AgentPanel";
import { useAgentOpen, useManagerOpen, useManagerTarget } from "./manager";
import { onManagerRequest } from "./managerRequests";
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
  const [agentOpen, setAgentOpen] = useAgentOpen();
  const target = useManagerTarget(route, params);
  // The side bar is the conversation with whoever works at this level: the
  // manager on a project or a sprint, the task's agents on a task. Each is
  // closed until the user opens it and stays as the user left it, across
  // pages and visits; nothing opens it on its own (owner, 2026-11-24).
  const onTask = route.level === "task";
  const taskId = onTask ? params.taskId : null;
  const panelOpen = onTask ? agentOpen : managerOpen;
  const setPanel = onTask ? setAgentOpen : setManagerOpen;
  const projectName = useProjectName(target.projectId);
  useEffect(() => onManagerRequest(() => setManagerOpen(true)), [setManagerOpen]);
  useLiveData({ projectId: target.projectId, poll: route.name === "workspace" });

  useEffect(() => {
    document.title = `${route.title} · Foreman`;
  }, [route]);

  let page;
  if (route.name === "not-found") {
    page = <NotFoundPage />;
  } else if (BUILT_PAGES[route.name]) {
    const Page = BUILT_PAGES[route.name];
    page = <Page params={params} routeName={route.name} />;
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
              <ManagerToggle open={panelOpen} word={onTask ? "Agent" : "Manager"} onToggle={() => setPanel(!panelOpen)} />
            ) : null
          }
        />
      }
      managerOpen={panelOpen}
      managerLabel={onTask ? "Agent" : "Manager"}
      manager={
        onTask ? (
          <AgentPanel key={taskId} task={target.task} onClose={() => setPanel(false)} />
        ) : target.hasManager ? (
          <ManagerPanel
            key={target.projectId || "no-project"}
            projectId={target.projectId}
            projectName={projectName}
            page={target.page}
            context={target.context}
            onClose={() => setPanel(false)}
          />
        ) : null
      }
    >
      {/* A new key resets page state when the page changes; the tabs of one
          page share a key, so its head stays put and is not loaded again. */}
      <React.Fragment key={pageKey(route.name, params)}>{page}</React.Fragment>
    </Shell>
  );
}
