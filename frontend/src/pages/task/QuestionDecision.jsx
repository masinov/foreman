import React, { useState } from "react";

import { useApiClient } from "../../api/ApiProvider";
import { errorSentence } from "../../api/client";
import { answerTask } from "../../api/tasks";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import { Surface } from "../../ui/Surface";
import { humanize } from "../../ui/format";
import { taskName } from "../shared/decisionWords";

/** The sentence an answer is acknowledged with, from the API's own words. */
export const answeredSentence = (task, result) => result?.message || `Answered ${taskName(task)}.`;

/**
 * The decision of a task whose agent asked a person something: the question,
 * its options with the recommendation marked and why, and a field for an
 * answer in a person's own words. A person answers with an option, with
 * their words, or both (ADR-0041 section 4). `onDecided(sentence)` runs once
 * the API accepted the answer.
 */
export function QuestionDecision({ task, onDecided }) {
  const client = useApiClient();
  const asked = task.question;
  const [option, setOption] = useState(null);
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [refusal, setRefusal] = useState(null);
  const recommended = asked.recommendation?.option;
  const ready = option !== null || text.trim() !== "";

  async function answer(event) {
    event.preventDefault();
    if (!ready) return;
    setPending(true);
    setRefusal(null);
    try {
      const result = await answerTask(client, task.id, { option, text: text.trim() });
      onDecided(answeredSentence(task, result));
    } catch (error) {
      setRefusal(errorSentence(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <Surface as="section" className="decision decision--question" aria-labelledby="task-decision">
      <form className="decision__body" onSubmit={answer} noValidate>
        <h2 className="decision__question" id="task-decision">
          {asked.question}
        </h2>
        <p className="decision__detail">
          {asked.role_id ? `${humanize(asked.role_id)} asked this` : "An agent asked this"}
          {asked.step ? ` at ${humanize(asked.step)}` : ""}. Its step goes on with your answer.
        </p>
        <fieldset className="question__options">
          <legend className="visually-hidden">Options</legend>
          {asked.options.map((words, index) => {
            const number = index + 1;
            return (
              <label className="question__option" key={number}>
                <input
                  type="radio"
                  className="checkbox"
                  name={`question-${task.id}`}
                  checked={option === number}
                  onChange={() => setOption(number)}
                  // A chosen option is cleared by choosing it again, so a
                  // person can still answer in words alone.
                  onClick={() => {
                    if (option === number) setOption(null);
                  }}
                />
                <span className="question__words">
                  {number}. {words}
                  {number === recommended ? <span className="question__recommended"> Recommended</span> : null}
                </span>
              </label>
            );
          })}
        </fieldset>
        {recommended ? (
          <p className="decision__detail question__why">
            Recommended: option {recommended}. {asked.recommendation.why}
          </p>
        ) : null}
        <Field
          label="Or answer in your own words"
          hint="Alone, or beside an option. Click a chosen option again to clear it."
          multiline
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        {refusal ? (
          <p className="notice notice--error" role="alert">
            {refusal}
          </p>
        ) : null}
        <div className="decision__actions question__actions">
          <Button variant="gold" type="submit" disabled={pending || !ready}>
            {pending ? "Recording…" : "Answer"}
          </Button>
        </div>
      </form>
    </Surface>
  );
}
