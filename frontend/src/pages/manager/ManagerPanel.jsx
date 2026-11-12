import React, { useEffect, useId, useRef, useState } from "react";

import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { plural } from "../../ui/format";
import { ReasonDialog } from "../task/ReasonDialog";
import { useConversation } from "./useConversation";

import "../../styles/manager.css";

/** "Bash, Bash, Read" as "Bash ×2, Read". */
function toolSummary(tools) {
  const counts = new Map();
  for (const name of tools) counts.set(name, (counts.get(name) || 0) + 1);
  return [...counts].map(([name, count]) => (count > 1 ? `${name} ×${count}` : name)).join(", ");
}

function Turn({ turn, onRetry, canRetry }) {
  const mine = turn.role === "user";
  return (
    <div className={`manager__turn manager__turn--${turn.role}`}>
      <div className="manager__who">{mine ? "You" : "Manager"}</div>
      {turn.text || turn.state === "streaming" ? (
        <p className="manager__text">
          {turn.text}
          {turn.state === "streaming" ? <span className="manager__cursor" aria-hidden="true" /> : null}
        </p>
      ) : null}
      {turn.tools.length > 0 ? <p className="manager__tools">Ran {toolSummary(turn.tools)}.</p> : null}
      {turn.state === "interrupted" ? <p className="manager__tools">This reply was cut short.</p> : null}
      {turn.state === "failed" ? (
        <p className="manager__failure" role="alert">
          <span>{turn.error}</span>
          {canRetry ? (
            <Button variant="quiet" inRow onClick={onRetry}>
              Retry
            </Button>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The manager side bar: one conversation per project. Everything the manager
 * says is shown as written; a change it makes is something it did through the
 * CLI, not something this panel can hold back, so nothing here asks to confirm
 * (the endpoints return no structured proposal).
 */
export function ManagerPanel({ projectId, projectName, page, context, onClose }) {
  const headingId = useId();
  const conversation = useConversation(projectId, context);
  const { turns, streaming } = conversation;
  const [draft, setDraft] = useState("");
  const [asking, setAsking] = useState(false);
  const thread = useRef(null);

  useEffect(() => {
    const node = thread.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [turns]);

  function submit(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || streaming || !projectId) return;
    setDraft("");
    conversation.send(text);
  }

  function onKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent?.isComposing) submit(event);
  }

  return (
    <section className="manager" aria-labelledby={headingId}>
      <div className="manager__head">
        <h2 className="manager__title" id={headingId}>
          Manager
        </h2>
        {projectName ? <span className="manager__project">{projectName}</span> : null}
        {page ? <span className="manager__where">You are on: {page}</span> : null}
        <Button variant="quiet" inRow className="manager__close" onClick={onClose}>
          Close
        </Button>
      </div>

      <div className="manager__thread" role="log" aria-live="polite" aria-busy={streaming} ref={thread}>
        {conversation.hasMore ? (
          <div className="manager__older">
            <Button variant="quiet" inRow onClick={conversation.loadOlder} disabled={conversation.loadingOlder}>
              {conversation.loadingOlder ? "Loading earlier messages" : "Earlier messages"}
            </Button>
            {conversation.olderError ? <span className="manager__error">{conversation.olderError}</span> : null}
          </div>
        ) : null}
        {conversation.loadError ? (
          <p className="manager__failure" role="alert">
            <span>{conversation.loadError}</span>
            <Button variant="quiet" inRow onClick={conversation.reloadHistory}>
              Retry
            </Button>
          </p>
        ) : null}
        {conversation.loading ? <p className="manager__quiet">Loading the conversation.</p> : null}
        {!conversation.loading && !conversation.loadError && turns.length === 0 ? (
          <p className="manager__quiet">No conversation yet. Ask about this project, or ask for a change.</p>
        ) : null}
        {turns.map((turn, index) => (
          <Turn key={turn.key} turn={turn} canRetry={index === turns.length - 1 && !streaming} onRetry={conversation.retry} />
        ))}
      </div>

      <form className="manager__composer" onSubmit={submit}>
        <Field
          label="Message to the manager"
          hideLabel
          multiline
          rows={2}
          placeholder="Ask about this project, or ask for a change"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          disabled={!projectId}
        />
        <div className="manager__actions">
          <Button variant="quiet" onClick={() => setAsking(true)} disabled={streaming || turns.length === 0}>
            Start a new conversation
          </Button>
          <Button type="submit" disabled={!draft.trim() || streaming || !projectId}>
            {streaming ? "Replying" : "Send"}
          </Button>
        </div>
      </form>

      <ReasonDialog
        open={asking}
        title="Start a new conversation?"
        effect={`This clears the conversation with the manager for ${projectName || "this project"}: ${plural(turns.length, "message")}. The manager will not remember it.`}
        confirm="Start a new conversation"
        doing="Clearing"
        run={conversation.clear}
        onClose={() => setAsking(false)}
        onDone={() => setAsking(false)}
      />
    </section>
  );
}
