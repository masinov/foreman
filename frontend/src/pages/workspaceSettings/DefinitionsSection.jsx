import React from "react";

import { SectionHeading } from "../../ui/SectionHeading";
import { RolesTab } from "../settings/RolesTab";
import { WorkflowsList } from "./WorkflowsList";

/**
 * Defaults for projects: the workspace's workflows and roles, edited here
 * with the editors a project has. A change reaches every project that keeps
 * no version of its own (ADR-0024, amendment of 2026-11-16).
 */
export function DefinitionsSection() {
  return (
    <section className="settings-block" aria-labelledby="defaults-title">
      <SectionHeading id="defaults-title" title="Defaults for projects" />
      <div className="definitions">
        <WorkflowsList />
        <RolesTab />
      </div>
    </section>
  );
}
