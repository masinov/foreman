import { WorkspacePage } from "../pages/workspace/WorkspacePage";

// Routes that have a rebuilt page. Every other route in ROUTES renders the
// shared "being rebuilt" page until its slice lands.
export const BUILT_PAGES = {
  workspace: WorkspacePage,
};
