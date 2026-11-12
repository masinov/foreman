import React, { useEffect } from "react";

import { getSprint } from "../api/sprints";
import { getTask } from "../api/tasks";
import { useResource } from "../api/useResource";
import { EngineMenu } from "../pages/shared/EngineMenu";
import { NotFoundPage } from "../pages/status/NotFoundPage";
import { RebuildingPage } from "../pages/status/RebuildingPage";
import { BUILT_PAGES } from "./pages";
import { paths } from "./paths";
import { Link, useRoute } from "./router";
import { Shell } from "./Shell";

/** The engine of the project a sprint or task belongs to. */
function EngineOf({ resourceKey, load }) {
  const { data } = useResource(resourceKey, load);
  return data?.project_id ? <EngineMenu projectId={data.project_id} /> : null;
}

function TopBarRight({ route, params }) {
  if (route.level === "sprint") {
    return (
      <EngineOf
        resourceKey={["sprint", params.sprintId]}
        load={(client, options) => getSprint(client, params.sprintId, options)}
      />
    );
  }
  if (route.level === "task") {
    return (
      <EngineOf
        resourceKey={["task", params.taskId]}
        load={(client, options) => getTask(client, params.taskId, options)}
      />
    );
  }
  if (route.level !== "workspace") return null;
  const current = route.name === "workspace-settings";
  return (
    <Link className="topbar__link" href={paths.workspaceSettings()} aria-current={current ? "page" : undefined}>
      Workspace settings
    </Link>
  );
}

export function App() {
  const { route, params } = useRoute();

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
    <Shell topBarRight={<TopBarRight route={route} params={params} />}>
      {/* A new key per address resets page state when the route changes. */}
      <React.Fragment key={`${route.name}:${JSON.stringify(params)}`}>{page}</React.Fragment>
    </Shell>
  );
}
