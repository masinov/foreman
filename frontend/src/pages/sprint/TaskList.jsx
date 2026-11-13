import React from "react";

import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Mono } from "../../ui/Mono";
import { StatusDot } from "../../ui/StatusDot";
import { Table } from "../../ui/Table";
import { formatMoney } from "../../ui/format";
import { TaskChecks } from "./TaskChecks";
import { orderTasks, stageOf, waitsForMerge } from "./taskStage";

/** The sprint's tasks as a table: what needs a person first, finished last. */
export function TaskList({ tasks, busy, onApprove }) {
  const columns = [
    {
      key: "stage",
      header: "Stage",
      className: "task-list__stage",
      render: (task) => {
        const { tone, word } = stageOf(task);
        return <StatusDot tone={tone}>{word}</StatusDot>;
      },
    },
    {
      key: "key",
      header: "Key",
      className: "task-list__key",
      render: (task) => <Mono quiet>{task.task_key || "—"}</Mono>,
    },
    {
      key: "title",
      header: "Task",
      render: (task) => (
        <Link className="row-link" href={paths.task(task.id)}>
          {task.title}
        </Link>
      ),
    },
    { key: "checks", header: "Checks", className: "task-list__checks", render: (task) => <TaskChecks task={task} /> },
    {
      key: "runs",
      header: "Runs",
      numeric: true,
      render: (task) => <Mono>{task.totals?.run_count ?? 0}</Mono>,
    },
    {
      key: "spend",
      header: "Spend",
      numeric: true,
      render: (task) => <Mono>{formatMoney(task.totals?.total_cost_usd)}</Mono>,
    },
    {
      key: "decision",
      header: <span className="visually-hidden">Decision</span>,
      className: "task-list__decision",
      render: (task) =>
        waitsForMerge(task) ? (
          <Button
            variant="gold-outline"
            inRow
            disabled={busy}
            aria-label={`Approve ${task.task_key || task.title}`}
            onClick={() => onApprove(task)}
          >
            Approve
          </Button>
        ) : null,
    },
  ];
  return <Table caption="Tasks" columns={columns} rows={orderTasks(tasks)} className="task-list" />;
}
