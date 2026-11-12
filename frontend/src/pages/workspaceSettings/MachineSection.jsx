import React from "react";

import { getMachine } from "../../api/access";
import { useResource } from "../../api/useResource";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { ReadOnlyRow } from "../settings/SettingRow";

/** This machine: where Foreman keeps its data and what is running. */
export function MachineSection() {
  const machine = useResource(["machine"], getMachine);
  return (
    <section className="settings-block" aria-labelledby="machine-title">
      <SectionHeading id="machine-title" title="This machine" note="Shown here, changed from a terminal." />
      {machine.error ? (
        <p className="notice notice--error" role="alert">
          {machine.error}
        </p>
      ) : null}
      {machine.data ? (
        <dl className="settings-section__rows machine">
          <ReadOnlyRow label="Database">
            <Mono quiet>{machine.data.database_path}</Mono>
          </ReadOnlyRow>
          <ReadOnlyRow label="Foreman version">
            <Mono quiet>{machine.data.version}</Mono>
          </ReadOnlyRow>
          <ReadOnlyRow label="Dashboard address">
            <Mono quiet>{machine.data.address}</Mono>
          </ReadOnlyRow>
        </dl>
      ) : null}
    </section>
  );
}
