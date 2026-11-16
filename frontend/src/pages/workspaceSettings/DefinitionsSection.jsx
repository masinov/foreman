import React from "react";

import { RolesTab } from "../settings/RolesTab";
import { WorkflowsList } from "./WorkflowsList";

/**
 * The workspace's workflows and roles, each a section of the page like the
 * others, edited with the editors a project has. A change reaches every
 * project that keeps no version of its own (ADR-0024, amendment of 2026-11-16).
 */
export function DefinitionsSection() {
  return (
    <>
      <WorkflowsList />
      <RolesTab />
    </>
  );
}
