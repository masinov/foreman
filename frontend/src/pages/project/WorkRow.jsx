import React from "react";

import { SprintHoldControls } from "../shared/SprintHoldControls";
import { StartWorker } from "../shared/StartWorker";
import { WorkStatus } from "../shared/WorkStatus";

/**
 * The project's work (ADR-0043): its active sprint's status line and the
 * sprint's controls, the same as the sprint page's. A project has no hold of
 * its own. "Start worker" appears only when no worker runs the project.
 */
export function WorkRow({ projectId, project, onChanged }) {
  const sprint = project?.active_sprint ?? null;
  const work = project?.work ?? null;
  if (!project) return null;
  return (
    <section className="work" aria-labelledby="work-title">
      <h2 className="work__label" id="work-title">
        Work
      </h2>
      <div className="work__state">
        <WorkStatus work={work} />
      </div>
      <SprintHoldControls sprintId={sprint?.id} work={work} onChanged={onChanged} />
      {work?.no_worker ? <StartWorker projectId={projectId} onChanged={onChanged} /> : null}
    </section>
  );
}
