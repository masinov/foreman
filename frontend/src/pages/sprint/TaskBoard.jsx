import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { paths } from "../../app/paths";
import { Link } from "../../app/router";
import { Button } from "../../ui/Button";
import { Caret } from "../../ui/Caret";
import { Mono } from "../../ui/Mono";
import { plural } from "../../ui/format";
import { TaskChecks } from "./TaskChecks";
import { boardColumns, waitsForMerge } from "./taskStage";

// Which columns a person folded or opened themselves, per project, in this
// browser. A column nobody chose for is folded when it is empty.
const FOLDED_KEY = (projectId) => `foreman.dashboard.board.folded.${projectId}`;

function readChoices(projectId) {
  try {
    const stored = JSON.parse(globalThis.localStorage?.getItem(FOLDED_KEY(projectId)) || "{}");
    return stored && typeof stored === "object" ? stored : {};
  } catch {
    return {};
  }
}

function writeChoices(projectId, choices) {
  try {
    globalThis.localStorage?.setItem(FOLDED_KEY(projectId), JSON.stringify(choices));
  } catch {
    // Not remembered; the board still folds for this visit.
  }
}

/** `[isFolded(column), toggle(column)]`: a person's choice, else folded when empty. */
function useFolding(projectId) {
  const [choices, setChoices] = useState(() => readChoices(projectId));
  const isFolded = useCallback(
    (column) => (column.key in choices ? Boolean(choices[column.key]) : column.tasks.length === 0),
    [choices],
  );
  const toggle = useCallback(
    (column) => {
      setChoices((current) => {
        const folded = column.key in current ? Boolean(current[column.key]) : column.tasks.length === 0;
        const next = { ...current, [column.key]: !folded };
        writeChoices(projectId, next);
        return next;
      });
    },
    [projectId],
  );
  return [isFolded, toggle];
}

// The board is never taller than what is left of the window below where it
// starts, so its sideways scrollbar is in view without scrolling down; a
// column with more cards than that scrolls them itself. A short window
// still gets a usable board.
const BOARD_MIN_HEIGHT = 320;
const BOARD_BOTTOM_GAP = 16;

/**
 * Keep the board within the window: its height limit, and whether columns
 * are cut off on either side (for the fade at that edge).
 */
function useBoardFit(ref, contentKey) {
  const [fit, setFit] = useState({ height: null, left: false, right: false, bar: 0 });
  const measure = useCallback(() => {
    const board = ref.current;
    if (!board) return;
    const top = board.getBoundingClientRect().top + window.scrollY;
    const height = Math.max(BOARD_MIN_HEIGHT, window.innerHeight - top - BOARD_BOTTOM_GAP);
    const left = board.scrollLeft > 1;
    const right = board.scrollLeft + board.clientWidth < board.scrollWidth - 1;
    const bar = board.offsetHeight - board.clientHeight;
    setFit((current) =>
      current.height === height && current.left === left && current.right === right && current.bar === bar
        ? current
        : { height, left, right, bar },
    );
  }, [ref]);

  useLayoutEffect(measure, [measure, contentKey]);
  useEffect(() => {
    const board = ref.current;
    if (!board) return undefined;
    window.addEventListener("resize", measure);
    board.addEventListener("scroll", measure, { passive: true });
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(measure) : null;
    observer?.observe(board);
    return () => {
      window.removeEventListener("resize", measure);
      board.removeEventListener("scroll", measure);
      observer?.disconnect();
    };
  }, [ref, measure]);
  return fit;
}

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

function Count({ column }) {
  return <span className={column.needsYou ? "board__count board__count--attention" : "board__count"}>{column.tasks.length}</span>;
}

function Column({ column, folded, onToggle, busy, onApprove }) {
  const bodyId = useId();
  if (folded) {
    // The whole strip opens it: the caret, then the name read downwards with
    // its count after it, as in an open column's heading.
    return (
      <section className="board__column board__column--folded" aria-label={column.label}>
        <button type="button" className="board__unfold" aria-expanded="false" aria-label={`Show ${column.label}`} onClick={onToggle}>
          <span className="board__folded-head">
            <Caret direction="right" />
          </span>
          <span className="board__folded-name">
            {column.label}
            <Count column={column} />
          </span>
        </button>
      </section>
    );
  }
  return (
    <section className="board__column" aria-label={column.label}>
      <h3 className="board__heading">
        {column.label}
        <Count column={column} />
        <button
          type="button"
          className="board__fold"
          aria-expanded="true"
          aria-controls={bodyId}
          aria-label={`Fold ${column.label}`}
          onClick={onToggle}
        >
          <Caret direction="left" />
        </button>
      </h3>
      <div className="board__cards" id={bodyId}>
        {column.tasks.map((task) => (
          <Card key={task.id} task={task} busy={busy} onApprove={onApprove} />
        ))}
      </div>
    </section>
  );
}

/**
 * One column per step of the project's workflow, Queued first and Done last.
 * The engine moves the cards; nothing here is draggable. A column folds to
 * a narrow strip with its name and count; an empty one starts folded, and a
 * person's own choice is remembered per project.
 *
 * The board fits in the window: a column with more cards than fit scrolls
 * them under its heading, so the sideways scrollbar stays in view; an edge
 * where columns are cut off fades out (owner, 2026-11-18).
 */
export function TaskBoard({ projectId, tasks, workflow, busy, onApprove }) {
  const columns = boardColumns(tasks, workflow);
  const cancelled = tasks.filter((task) => task.status === "cancelled").length;
  const [isFolded, toggle] = useFolding(projectId || "");
  const boardRef = useRef(null);
  const frameRef = useRef(null);
  const layout = columns.map((column) => `${column.key}:${column.tasks.length}:${isFolded(column) ? 1 : 0}`).join(",");
  const fit = useBoardFit(boardRef, layout);
  const frameClass = ["board-frame", fit.left ? "board-frame--cut-left" : "", fit.right ? "board-frame--cut-right" : ""]
    .filter(Boolean)
    .join(" ");
  // Measured values reach the stylesheet as custom properties on the frame.
  useLayoutEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;
    if (fit.height) frame.style.setProperty("--board-height", `${fit.height}px`);
    frame.style.setProperty("--board-scrollbar", `${fit.bar}px`);
  }, [fit.height, fit.bar]);
  return (
    <>
      <div className={frameClass} ref={frameRef}>
        <div className="board" ref={boardRef}>
          {columns.map((column) => (
            <Column
              key={column.key}
              column={column}
              folded={isFolded(column)}
              onToggle={() => toggle(column)}
              busy={busy}
              onApprove={onApprove}
            />
          ))}
        </div>
      </div>
      {cancelled > 0 ? (
        <p className="quiet">{plural(cancelled, "cancelled task")} not shown on the board.</p>
      ) : null}
    </>
  );
}
