import { useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";

/**
 * A project's engine as the workspace reports it: `{ state, task_id, ... }`,
 * or null until it is known. The same read the top bar's engine menu makes,
 * so asking here costs no second request.
 */
export function useProjectEngine(projectId) {
  const workspace = useResource(["workspace"], getWorkspace, { enabled: Boolean(projectId) });
  return workspace.data?.projects.find((project) => project.id === projectId)?.engine ?? null;
}
