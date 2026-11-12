import React from "react";

import { listRunners } from "../../api/access";
import { useDelayedFlag, useResource } from "../../api/useResource";
import { Mono } from "../../ui/Mono";
import { SectionHeading } from "../../ui/SectionHeading";
import { Table } from "../../ui/Table";

function Models({ runner }) {
  if (runner.models.length === 0 && !runner.uses_default) return <span className="settings-block__aside">None named</span>;
  return (
    <>
      {runner.models.map((model, index) => (
        <React.Fragment key={model}>
          {index > 0 ? ", " : null}
          <Mono>{model}</Mono>
        </React.Fragment>
      ))}
      {runner.uses_default ? (
        <span className="settings-block__aside">
          {runner.models.length > 0 ? " · " : ""}its own default for roles that name none
        </span>
      ) : null}
    </>
  );
}

/** Runners: the programs that run agents, as the server finds them. */
export function RunnersSection() {
  const runners = useResource(["runners"], listRunners);
  const placeholder = useDelayedFlag(runners.loading && !runners.data);
  return (
    <section className="settings-block" aria-labelledby="runners-title">
      <SectionHeading id="runners-title" title="Runners" note="The programs that run agents." />
      {runners.error ? (
        <p className="notice notice--error" role="alert">
          {runners.error}
        </p>
      ) : null}
      {runners.data || placeholder ? (
        <Table
          caption="Runners"
          rows={runners.data ?? []}
          placeholderRows={placeholder ? 2 : null}
          columns={[
            { key: "name", header: "Runner", render: (runner) => runner.name },
            {
              key: "found",
              header: "On this machine",
              render: (runner) =>
                runner.found ? (
                  <>
                    <span className="tone-passed">Found</span>
                    <span className="settings-block__aside"> · </span>
                    <Mono quiet>{runner.path}</Mono>
                  </>
                ) : (
                  <>
                    <span className="tone-attention">Not found</span>
                    <span className="settings-block__aside"> · no {runner.executable} on the path</span>
                  </>
                ),
            },
            { key: "models", header: "Models roles ask for", render: (runner) => <Models runner={runner} /> },
          ]}
        />
      ) : null}
    </section>
  );
}
