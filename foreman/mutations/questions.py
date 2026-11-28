"""A person's answer to the question an agent asked (ADR-0041 section 4).

The question is on the record of the run that asked it, and the task waits,
blocked, at the step that asked. The answer is recorded here with who gave it
and when: a run of its own, so the Activity lists it, an event, and the task
left ``in_progress`` at the same step for the project's engine to run again
with the answer (ADR-0011). Nothing runs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.models import Run, Task
from ..domain.outcomes import ASK
from ..definitions.question import (
    ANSWER_BACKEND,
    ANSWER_KIND,
    ANSWER_ROLE,
    ANSWERED_EVENT,
    QUESTION_BLOCKED_REASON,
    AnswerError,
    answer_words,
    question_of,
    resolve_answer,
)
from ..history.records import RunRecords
from ..notifications.delivery import NotificationDispatcher
from .base import MutationBase, MutationError


@dataclass(frozen=True)
class QuestionAnswer:
    """An answer recorded, and where the task goes on."""

    task: Task
    step: str
    answer: dict[str, Any]


def pending_question(task: Task, runs: list[Run]) -> tuple[Run, dict[str, Any]] | None:
    """The run that asked the question a task waits on, and the question; None when it waits on none."""

    if task.status != "blocked" or (task.blocked_reason or "") != QUESTION_BLOCKED_REASON:
        return None
    for run in reversed(runs):
        if run.outcome == ASK and (question := question_of(run.record)) is not None:
            return run, question
        if run.role_id == ANSWER_ROLE:
            return None
    return None


class QuestionMutations(MutationBase):
    """Answering an agent's question."""

    def answer_question(
        self, task: Task, *, option: int | None = None, text: str | None = None
    ) -> QuestionAnswer:
        """Answer the question a task waits on with an option, with words, or both.

        The task is left at the step that asked, for the project's engine to
        run again with the answer.
        """

        found = pending_question(task, self.store.list_runs(task_id=task.id))
        if found is None:
            raise MutationError(f"Task {task.id} waits for no answer to a question.")
        asked, question = found
        try:
            answer = resolve_answer(question, option=option, text=text)
        except AnswerError as exc:
            raise MutationError(str(exc)) from exc
        if not self.store.claim_answered_question(task.id, QUESTION_BLOCKED_REASON):
            raise MutationError(
                f"Task {task.id}'s question was answered meanwhile, or the task no longer waits."
            )
        now = self._now().isoformat()
        who = (self.actor or "").strip() or self.via
        answer = {**answer, "answered_by": who, "answered_via": self.via, "answered_at": now}
        step = asked.workflow_step or task.workflow_current_step or ""
        records = RunRecords(self.store, NotificationDispatcher(self.store))
        run = records.create_system_run(
            task,
            workflow_step=step,
            outcome="answered",
            detail=answer_words(answer),
            role_id=ANSWER_ROLE,
            agent_backend=ANSWER_BACKEND,
        )
        run.record = {
            "kind": ANSWER_KIND,
            "fields": {**answer, "question": question["question"], "question_run_id": asked.id},
        }
        self.store.save_run(run)
        records.emit_event(
            run,
            ANSWERED_EVENT,
            {"step": step, "question_run_id": asked.id, "question": question["question"], **answer},
        )
        task.status = "in_progress"
        task.blocked_reason = None
        task.workflow_current_step = step
        self.store.save_task(task)
        decided = self.store.get_task(task.id) or task
        return QuestionAnswer(task=decided, step=step, answer=answer)
