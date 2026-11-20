import React from "react";

import { useOptionalNavigate } from "../app/router";

/**
 * A table: one line under the column headers, faint lines between rows, none
 * above the first row or below the last. `tinted` is the variant that sits
 * inside the tinted surface, with its inset row line.
 *
 * `columns` are `{ key, header, render(row), className?, numeric? }`; a
 * numeric column is set to the right, header and figures alike. `selected(row)`
 * marks the row a person picked (its control says so to assistive
 * technology; the row is shaded). With `onRowClick(row)` the whole row
 * picks, not only its control. `arrived(row)` marks a row that was not in
 * the list a moment ago, which opens into place instead of jumping in. While
 * `placeholderRows` is a number, that many placeholder rows stand in for the
 * data (callers show them only after 200 ms of loading).
 *
 * With `rowHref(row)` the whole row leads to that page: a plain click
 * anywhere on it that is not on a control of its own goes there. A row's
 * own link stays the way in for the keyboard and for opening a new tab.
 *
 * The table scrolls inside its own container, so the page never scrolls
 * sideways at phone width.
 */
const cellClass = (column) =>
  [column.className, column.numeric ? "table__number" : ""].filter(Boolean).join(" ") || undefined;

export function Table({
  caption,
  columns,
  rows = [],
  rowKey = (row) => row.id,
  selected = null,
  onRowClick = null,
  rowHref = null,
  arrived = null,
  tinted = false,
  hideHeader = false,
  placeholderRows = null,
  className = "",
}) {
  const navigate = useOptionalNavigate();
  const classes = ["table", tinted ? "table--tinted" : "", className].filter(Boolean).join(" ");
  const follow = (row) => (event) => {
    const href = rowHref(row);
    if (!href || !navigate) return;
    if (event.target.closest?.("a, button, input, select, textarea, summary")) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (event.view?.getSelection?.()?.toString()) return;
    navigate(href);
  };
  const placeholders = typeof placeholderRows === "number" && placeholderRows > 0;
  return (
    <div className="table-scroll">
      <table className={classes} aria-busy={placeholders ? "true" : undefined}>
        {caption ? <caption className="visually-hidden">{caption}</caption> : null}
        <thead className={hideHeader ? "visually-hidden" : undefined}>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={cellClass(column)}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {placeholders
            ? Array.from({ length: placeholderRows }, (_, index) => (
                <tr key={`placeholder-${index}`} className="table__placeholder" aria-hidden="true">
                  {columns.map((column) => (
                    <td key={column.key} className={cellClass(column)}>
                      <span className="table__placeholder-bar" />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  className={
                    [
                      selected?.(row) ? "table__row--selected" : "",
                      onRowClick || rowHref?.(row) ? "table__row--pickable" : "",
                      arrived?.(row) ? "table__row--arrived" : "",
                    ]
                      .filter(Boolean)
                      .join(" ") || undefined
                  }
                  onClick={onRowClick ? () => onRowClick(row) : rowHref ? follow(row) : undefined}
                >
                  {columns.map((column) => (
                    <td key={column.key} className={cellClass(column)}>
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
