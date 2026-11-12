import React from "react";

import { Mono } from "../../ui/Mono";
import { shortSha } from "../../ui/format";
import { checksOf } from "./taskStage";

/** tests · review · commit, from the task's completion evidence. */
export function TaskChecks({ task }) {
  const { parts, commit } = checksOf(task);
  const sha = shortSha(commit);
  if (parts.length === 0 && !sha) return <span className="quiet">Not checked yet</span>;
  return (
    <span className="checks">
      {parts.map((part, index) => (
        <React.Fragment key={part.key}>
          {index > 0 ? " · " : ""}
          <span className={`checks__${part.tone}`}>{part.text}</span>
        </React.Fragment>
      ))}
      {sha ? (
        <>
          {parts.length ? " · " : ""}
          <Mono quiet>{sha}</Mono>
        </>
      ) : null}
    </span>
  );
}
