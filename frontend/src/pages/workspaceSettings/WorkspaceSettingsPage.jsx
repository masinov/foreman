import React from "react";

import { AccessSection } from "./AccessSection";
import { ChannelsSection } from "./ChannelsSection";
import { DefinitionsSection } from "./DefinitionsSection";
import { MachineSection } from "./MachineSection";
import { RunnersSection } from "./RunnersSection";

import "../../styles/settings.css";
import "../../styles/workspaceSettings.css";

/**
 * Workspace settings (docs/design/dashboard-v7/15-workspace-settings.html):
 * what is shared by every project and by the people and systems around them.
 * Creating and editing workflows and roles is not here; their files are.
 */
export function WorkspaceSettingsPage() {
  return (
    <div className="workspace-settings">
      <h1 className="page-title">Workspace settings</h1>
      <DefinitionsSection />
      <AccessSection />
      <ChannelsSection />
      <RunnersSection />
      <MachineSection />
    </div>
  );
}
