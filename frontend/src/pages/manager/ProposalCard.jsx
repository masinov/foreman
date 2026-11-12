import React, { useState } from "react";

import { useApiClient, useDataRefresh } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { confirmProposal, declineProposal, getProposal } from "../../api/proposals";
import { useResource } from "../../api/useResource";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { proposalHeading, proposalOutcome, proposalRows } from "./proposalWords";

function RowText({ row }) {
  return (
    <>
      {row.task ? (
        <>
          <Mono>{row.task.key}</Mono>
          {row.task.title ? ` ${row.task.title}` : null}
        </>
      ) : null}
      {row.task && row.text ? " " : null}
      {row.text}
    </>
  );
}

/**
 * A proposal the manager made, in the conversation: what it will create,
 * change and leave, with "Not now" and "Confirm" while it waits, and what
 * happened once it was decided. Deciding reloads the page's data.
 */
export function ProposalCard({ proposalId }) {
  const client = useApiClient();
  const { refresh } = useDataRefresh();
  const { data, error, reload } = useResource(["proposal", proposalId], (api, options) => getProposal(api, proposalId, options));
  const [decided, setDecided] = useState(null);
  const [pending, setPending] = useState(null);
  const [refusal, setRefusal] = useState(null);
  const proposal = decided || data;

  async function decide(kind) {
    setPending(kind);
    setRefusal(null);
    try {
      const result = await (kind === "confirm" ? confirmProposal : declineProposal)(client, proposalId);
      setDecided(result);
      refresh();
    } catch (failure) {
      setRefusal(errorSentence(failure));
      reload();
    } finally {
      setPending(null);
    }
  }

  if (!proposal) {
    return (
      <div className="proposal">
        <p className="proposal__head">{error ? `This proposal could not be shown. ${error}` : "Loading the proposal."}</p>
      </div>
    );
  }

  const outcome = proposalOutcome(proposal);
  const waiting = proposal.state === "proposed";
  return (
    <div className="proposal" data-state={proposal.state}>
      <p className="proposal__head">{proposalHeading(proposal)}</p>
      <dl className="proposal__rows">
        {proposalRows(proposal).map((row, index) => (
          <React.Fragment key={index}>
            <dt className="proposal__term">{row.term}</dt>
            <dd className={row.quiet ? "proposal__what proposal__what--quiet" : "proposal__what"}>
              <RowText row={row} />
            </dd>
          </React.Fragment>
        ))}
      </dl>
      {refusal ? (
        <p className="proposal__outcome proposal__outcome--failed" role="alert">
          {refusal}
        </p>
      ) : null}
      {outcome ? (
        <p className={`proposal__outcome proposal__outcome--${outcome.tone}`} role="status">
          {outcome.text}
        </p>
      ) : null}
      {waiting ? (
        <div className="proposal__actions">
          <Button inRow disabled={Boolean(pending)} onClick={() => decide("decline")}>
            {pending === "decline" ? "Declining" : "Not now"}
          </Button>
          <Button inRow variant="gold-outline" disabled={Boolean(pending)} onClick={() => decide("confirm")}>
            {pending === "confirm" ? "Applying" : "Confirm"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
