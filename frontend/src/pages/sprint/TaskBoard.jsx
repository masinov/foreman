import React from "react";

import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { plural } from "../../ui/format";
import { TaskChecks } from "./TaskChecks";
import { boardColumns, waitsForMerge } from "./taskStage";

function Card({ task, busy, onApprove }) {
  return (
    <article className={task.status === "done" ? "board-card board-card--done" : "board-card"}>
      <div className="board-card__head">
        <Mono quiet>{task.task_key || "—"}</Mono>
        <span className="board-card__checks">
          <TaskChecks task={task} />
        </span>
      </div>
      <Link className="row-link" href={paths.task(task.id)}>
        {task.title}
      </Link>
      {waitsForMerge(task) ? (
        <Button
          variant="gold-outline"
          inRow
          className="board-card__approve"
          disabled={busy}
          aria-label={`Approve ${task.task_key || task.title}`}
          onClick={() => onApprove(task)}
        >
          Approve
        </Button>
      ) : null}
    </article>
  );
}

/**
 * One column per step of the project's workflow, Queued first and Done last.
 * The engine moves the cards; nothing here is draggable.
 */
export function TaskBoard({ tasks, workflow, busy, onApprove }) {
  const columns = boardColumns(tasks, workflow);
  const cancelled = tasks.filter((task) => task.status === "cancelled").length;
  return (
    <>
      <div className="board">
        {columns.map((column) => (
          <section
            key={column.key}
            className={column.tasks.length === 0 ? "board__column board__column--empty" : "board__column"}
            aria-label={column.label}
          >
            <h3 className="board__heading">
              {column.label}
              <span className={column.needsYou ? "board__count board__count--attention" : "board__count"}>
                {column.tasks.length}
              </span>
            </h3>
            {column.tasks.length === 0 ? (
              <p className="board__none">None</p>
            ) : (
              column.tasks.map((task) => <Card key={task.id} task={task} busy={busy} onApprove={onApprove} />)
            )}
          </section>
        ))}
      </div>
      {cancelled > 0 ? (
        <p className="quiet">{plural(cancelled, "cancelled task")} not shown on the board.</p>
      ) : null}
    </>
  );
}
