import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { acceptTask, declineTask } from "../../api/backlog";
import { errorSentence } from "../../api/client";
import { approveTask, denyTask, unblockTask } from "../../api/tasks";
import { paths } from "../../app/paths";
import { Link, useOptionalNavigate } from "../../app/router";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { Surface } from "../../ui/Surface";
import { formatDay, formatDuration, humanize } from "../../ui/format";
import { decisionSentence, taskName } from "../shared/decisionWords";
import { MERGE_APPROVAL, versionToken, versionWords } from "../shared/gateVersion";
import { ReasonDialog } from "../shared/ReasonDialog";
import {
  branchWords,
  codeReview,
  DECISIONS,
  decisionOf,
  filedBy,
  reviewWords,
  testsWords,
} from "./taskWords";
import { runBy, runResult, runSeconds } from "../shared/activityWords";

/** The calls behind the two buttons, per kind of decision. */
const CALLS = {
  [DECISIONS.merge]: { approve: approveTask, sendBack: denyTask },
  [DECISIONS.plan]: { approve: approveTask, sendBack: denyTask },
  [DECISIONS.gate]: { approve: approveTask, sendBack: denyTask },
  [DECISIONS.accept]: {
    approve: acceptTask,
    sendBack: (client, taskId, reason) => declineTask(client, taskId, { reason }),
  },
  [DECISIONS.unblock]: {
    approve: (client, taskId) => unblockTask(client, taskId, null),
    sendBack: unblockTask,
  },
};

const DONE_WORDS = {
  [DECISIONS.accept]: { approve: "Accepted. It runs with the rest of the sprint.", sendBack: "Declined." },
  [DECISIONS.unblock]: {
    approve: "Unblocked. The task is back in the queue.",
    sendBack: "Unblocked with guidance. The task is back in the queue.",
  },
};

function Fact({ tone, word, children }) {
  return (
    <li className="decision__fact">
      {word ? <span className={`tone-${tone}`}>{word}</span> : null}
      {word && children ? " " : null}
      {children}
    </li>
  );
}

function MergeFacts({ checks }) {
  if (!checks) return null;
  const tests = testsWords(checks.facts.tests);
  const review = codeReview(checks);
  const branch = branchWords(checks.facts.branch);
  const reviewed = review ? reviewWords(review) : null;
  return (
    <>
      <Fact tone={tests.tone} word={`Tests ${tests.word.toLowerCase()}`}>
        {tests.detail}
      </Fact>
      {reviewed ? (
        <Fact tone={reviewed.tone} word={`Review ${reviewed.word.toLowerCase()}`}>
          {[review.model ? `by ${review.model}` : "", review.current === true ? "same commit" : review.current === false ? "on an older commit" : ""]
            .filter(Boolean)
            .join(", ")}
        </Fact>
      ) : (
        <Fact tone="idle" word="No review recorded" />
      )}
      <Fact tone="idle">{`Branch is ${branch.word.charAt(0).toLowerCase()}${branch.word.slice(1)}`}</Fact>
    </>
  );
}

/** The run that led to the gate: the last one at another step. */
function StepBeforeFacts({ task }) {
  const before = [...(task.runs ?? [])]
    .filter((run) => run.workflow_step && run.workflow_step !== task.workflow_current_step)
    .sort((a, b) => String(a.started_at || a.created_at || "").localeCompare(String(b.started_at || b.created_at || "")))
    .pop();
  return (
    <>
      {before ? (
        <Fact tone={runResult(before).tone} word={`${humanize(before.workflow_step)}: ${runResult(before).word.toLowerCase()}`}>
          {[runBy(before, task) ? `by ${runBy(before, task)}` : "", formatDuration(runSeconds(before)) ? `in ${formatDuration(runSeconds(before))}` : ""]
            .filter(Boolean)
            .join(" ")}
        </Fact>
      ) : null}
      <li className="decision__fact">
        <Link href={paths.taskActivity(task.id)}>Read its output under Activity</Link>
      </li>
    </>
  );
}

function AcceptFacts({ task }) {
  const who = filedBy(task);
  const when = formatDay(task.created_at);
  return (
    <>
      {who || when ? <Fact tone="idle">{["Filed", who ? `by ${who}` : "", when ? `on ${when}` : ""].filter(Boolean).join(" ")}</Fact> : null}
      {task.source?.url ? (
        <li className="decision__fact">
          <a href={task.source.url} target="_blank" rel="noreferrer">
            {task.source.external_ref || "Where it was filed"}
          </a>
        </li>
      ) : null}
      <Fact tone="idle">{`Type: ${humanize(task.task_type).toLowerCase()}`}</Fact>
    </>
  );
}

function UnblockFacts({ task }) {
  const last = [...(task.runs ?? [])]
    .sort((a, b) => String(a.started_at || a.created_at || "").localeCompare(String(b.started_at || b.created_at || "")))
    .pop();
  return (
    <>
      {task.workflow_current_step ? <Fact tone="idle">{`Stopped at ${humanize(task.workflow_current_step)}`}</Fact> : null}
      {last ? (
        <Fact tone={runResult(last).tone} word={`Last run: ${humanize(last.workflow_step)}, ${runResult(last).word.toLowerCase()}`}>
          {runBy(last, task) ? `by ${runBy(last, task)}` : ""}
        </Fact>
      ) : null}
    </>
  );
}

function Facts({ kind, task, checks }) {
  switch (kind) {
    case DECISIONS.merge:
      return <MergeFacts checks={checks} />;
    case DECISIONS.plan:
    case DECISIONS.gate:
      return <StepBeforeFacts task={task} />;
    case DECISIONS.accept:
      return <AcceptFacts task={task} />;
    default:
      return <UnblockFacts task={task} />;
  }
}

const GATE_KINDS = new Set([DECISIONS.merge, DECISIONS.plan, DECISIONS.gate]);

/**
 * The version the person is approving, and, when the gate's version has
 * changed since it was shown, a plain line that says so with a way to look
 * at the new one. `seen` is `useSeenGateVersion` of the task page.
 */
function VersionFacts({ seen, onLook }) {
  if (!seen?.version) return null;
  const shown = versionWords(seen.version);
  if (!shown) return null;
  const merge = seen.version.kind === MERGE_APPROVAL;
  const now = versionWords(seen.current);
  return (
    <>
      <li className="decision__fact">
        Approving <Mono>{shown}</Mono>
      </li>
      {seen.moved ? (
        <li className="decision__fact decision__moved">
          <span className="tone-attention">{merge ? "The branch moved since" : "The plan changed since"}</span>
          {now ? (
            <>
              {": it is now at "}
              <Mono>{now}</Mono>
            </>
          ) : null}
          {". "}
          <Button variant="quiet" inRow onClick={onLook}>
            {merge ? `Look at ${now}` : "Look at the new plan"}
          </Button>
        </li>
      ) : null}
    </>
  );
}

/**
 * The decision, on the tinted surface, only while the task waits for a
 * person: the question, the facts that bear on it, a way to send it back
 * (asking for the words that go with it) and the one filled gold button.
 * `onDecided(sentence)` runs once the API accepted the decision.
 *
 * At a gate the approval names the version the person is looking at
 * (`seen.version`), not the one the last background reload read; the
 * server refuses it if the branch or the plan has changed since.
 */
export function Decision({ task, checks, seen = null, onDecided }) {
  const client = useApiClient();
  const navigate = useOptionalNavigate();
  const [pending, setPending] = useState(false);
  const [refusal, setRefusal] = useState(null);
  const [sendingBack, setSendingBack] = useState(false);
  const decision = decisionOf(task, checks);
  if (!decision) return null;
  const calls = CALLS[decision.kind];
  const done = DONE_WORDS[decision.kind];
  const atGate = GATE_KINDS.has(decision.kind);

  async function approve() {
    setPending(true);
    setRefusal(null);
    try {
      const token = atGate ? versionToken(seen?.version ?? task.gate_version) : null;
      const result = await calls.approve(client, task.id, token ? { version: token } : undefined);
      onDecided(done?.approve ?? decisionSentence(taskName(task), result));
    } catch (error) {
      setRefusal(errorSentence(error));
      // The version may have changed under the page: read the new one.
      onDecided();
    } finally {
      setPending(false);
    }
  }

  // Looking at the new version takes it as the one approved, and shows it:
  // the diff for a merge, the plan's output for a plan.
  function look() {
    seen?.look();
    setRefusal(null);
    const where = seen?.version?.kind === MERGE_APPROVAL ? paths.taskChanges(task.id) : paths.taskActivity(task.id);
    navigate?.(where);
  }

  return (
    <Surface as="section" className="decision" aria-labelledby="task-decision">
      <div className="decision__body">
        <h2 className="decision__question" id="task-decision">
          {decision.question}
        </h2>
        {decision.detail ? <p className="decision__detail">{decision.detail}</p> : null}
        <ul className="decision__facts">
          <Facts kind={decision.kind} task={task} checks={checks} />
          {atGate ? <VersionFacts seen={seen} onLook={look} /> : null}
        </ul>
        {refusal ? (
          <p className="notice notice--error" role="alert">
            {refusal}
          </p>
        ) : null}
      </div>
      <div className="decision__actions">
        <Button disabled={pending} onClick={() => setSendingBack(true)}>
          {decision.sendBack.label}
        </Button>
        <Button variant="gold" disabled={pending} onClick={approve}>
          {pending ? "Recording…" : decision.approve}
        </Button>
      </div>
      <ReasonDialog
        open={sendingBack}
        title={decision.sendBack.title}
        effect={decision.sendBack.effect}
        ask={decision.sendBack.ask}
        hint={decision.sendBack.hint}
        required={decision.sendBack.required}
        confirm={decision.sendBack.label}
        doing="Recording…"
        run={(text) => calls.sendBack(client, task.id, text)}
        onClose={() => setSendingBack(false)}
        onDone={(result) => {
          setSendingBack(false);
          onDecided(done?.sendBack ?? decisionSentence(taskName(task), result, { sentBack: true }));
        }}
      />
    </Surface>
  );
}
