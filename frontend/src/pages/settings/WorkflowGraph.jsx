import React from "react";

// Geometry of the drawing, in SVG units. The rail of steps runs down the
// middle; lines that leave it for another step run in lanes to its left, the
// way a branch is drawn beside the trunk.
const ROW = 46;
const TOP = 20;
const LANE = 14;
const RADIUS = 5;
const TEXT_WIDTH = 300;
const TURN = 5;

const y = (row) => TOP + row * ROW;

/**
 * Put each line in a lane. A line is every route into one step from one side
 * (from below it, or from above it): `{ target, back, sources }`. Two lines
 * share a lane when the rows they cover do not overlap.
 */
function lanes(lines) {
  const taken = [];
  const sorted = [...lines].sort((a, b) => a.top - b.top || a.bottom - b.bottom);
  for (const line of sorted) {
    let lane = 0;
    while (taken[lane]?.some((other) => !(line.bottom < other.top || line.top > other.bottom))) lane += 1;
    (taken[lane] ??= []).push(line);
    line.lane = lane;
  }
  return taken.length;
}

/**
 * A workflow drawn as a graph: the steps in order on a rail, a task going
 * down it, and a line beside the rail wherever a task leaves the order, back
 * to an earlier step or ahead to a later one. Under each step, the same in
 * words. `rows` are `{ key, title, who, routes: [{ to, words }], stops: [words], nexts: [words] }`
 * with `to` a row index; `end` adds the closing row a task finishes at.
 */
export function WorkflowGraph({ rows, end, selected, onSelect, label }) {
  const count = rows.length + (end ? 1 : 0);
  const byTarget = new Map();
  rows.forEach((row, index) => {
    for (const route of row.routes) {
      const back = route.to < index;
      const id = `${back ? "b" : "a"}${route.to}`;
      const line = byTarget.get(id) ?? { target: route.to, back, sources: [] };
      if (!line.sources.includes(index)) line.sources.push(index);
      byTarget.set(id, line);
    }
  });
  const lines = [...byTarget.values()].map((line) => ({
    ...line,
    top: Math.min(line.target, ...line.sources),
    bottom: Math.max(line.target, ...line.sources),
  }));
  const laneCount = lanes(lines);
  const rail = laneCount * LANE + LANE;
  const textX = rail + RADIUS + 10;
  const width = textX + TEXT_WIDTH;
  const height = TOP + (count - 1) * ROW + 30;
  const lineX = (line) => rail - LANE - line.lane * LANE;

  const sentence = (row) =>
    [
      ...Object.entries(
        row.routes.reduce((groups, route) => {
          (groups[route.to] ??= []).push(route.words);
          return groups;
        }, {}),
      ).map(([to, words]) => `${words.join(", ")} ${Number(to) < rows.indexOf(row) ? "↩" : "↪"} ${Number(to) + 1}`),
      ...(row.nexts?.length ? [`${row.nexts.join(", ")} ↓ ${rows.indexOf(row) + 2}`] : []),
      ...(row.stops.length ? [`${row.stops.join(", ")}: waits for a person`] : []),
    ].join("  ·  ");

  return (
    <svg className="wf-graph" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="group" aria-label={label}>
      <line className="wf-graph__rail" x1={rail} y1={y(0)} x2={rail} y2={y(count - 1)} />
      {lines.map((line) => {
        const x = lineX(line);
        const targetY = y(line.target);
        return (
          <g key={`${line.back}-${line.target}`} className={line.back ? "wf-graph__line" : "wf-graph__line wf-graph__line--ahead"}>
            <line x1={x} y1={y(line.top) + TURN} x2={x} y2={y(line.bottom) - TURN} />
            {[line.target, ...line.sources].map((row) => {
              const rowY = y(row);
              const bend = row === line.top ? TURN : row === line.bottom ? -TURN : 0;
              return (
                <path
                  key={row}
                  d={
                    bend
                      ? `M ${rail - RADIUS} ${rowY} H ${x + TURN} Q ${x} ${rowY} ${x} ${rowY + bend}`
                      : `M ${rail - RADIUS} ${rowY} H ${x}`
                  }
                />
              );
            })}
            <path className="wf-graph__arrow" d={`M ${rail - RADIUS - 1} ${targetY} l -6 -3.5 v 7 z`} />
          </g>
        );
      })}
      {rows.map((row, index) => (
        <g
          key={row.key}
          className={row.key === selected ? "wf-graph__step wf-graph__step--selected" : "wf-graph__step"}
          role="button"
          tabIndex={0}
          aria-pressed={row.key === selected}
          aria-label={`Step ${index + 1}: ${row.title}`}
          onClick={() => onSelect(row.key)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onSelect(row.key);
            }
          }}
        >
          <rect className="wf-graph__hit" x={textX - 6} y={y(index) - 15} width={TEXT_WIDTH} height={ROW - 6} rx="3" />
          <circle className="wf-graph__node" cx={rail} cy={y(index)} r={RADIUS} />
          <text className="wf-graph__title" x={textX} y={y(index) + 4}>
            <tspan className="wf-graph__number">{index + 1}</tspan>
            <tspan dx="8">{row.title}</tspan>
            <tspan className="wf-graph__who" dx="8">
              {row.who}
            </tspan>
          </text>
          <text className="wf-graph__words" x={textX} y={y(index) + 20}>
            {sentence(row)}
          </text>
        </g>
      ))}
      {end ? (
        <g className="wf-graph__end">
          <circle className="wf-graph__node" cx={rail} cy={y(rows.length)} r={RADIUS} />
          <text className="wf-graph__title" x={textX} y={y(rows.length) + 4}>
            Done
          </text>
        </g>
      ) : null}
    </svg>
  );
}
