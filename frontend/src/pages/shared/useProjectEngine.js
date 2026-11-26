import { useResource } from "../../api/useResource";
import { getWorkspace } from "../../api/workspace";

/**
 * A project's worker as the workspace reports it (`{ state, task_id, ... }`),
 * or null until it is known: whether one runs the project, and on which task.
 * The same read the top bar's work menu makes, so asking here costs no second
 * request. Whether the work may go on is its holds' to say (ADR-0043).
 */
export function useProjectEngine(projectId) {
  const workspace = useResource(["workspace"], getWorkspace, { enabled: Boolean(projectId) });
  return workspace.data?.projects.find((project) => project.id === projectId)?.engine ?? null;
}
