import React from "react";

/**
 * A table: one line under the column headers, faint lines between rows, none
 * above the first row or below the last. `tinted` is the variant that sits
 * inside the tinted surface, with its inset row line.
 *
 * `columns` are `{ key, header, render(row), className?, numeric? }`; a
 * numeric column is set to the right, header and figures alike. `selected(row)`
 * marks the row a person picked (its control says so to assistive
 * technology; the row is shaded). While
 * `placeholderRows` is a number, that many placeholder rows stand in for the
 * data (callers show them only after 200 ms of loading).
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
  tinted = false,
  hideHeader = false,
  placeholderRows = null,
  className = "",
}) {
  const classes = ["table", tinted ? "table--tinted" : "", className].filter(Boolean).join(" ");
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
                <tr key={rowKey(row)} className={selected?.(row) ? "table__row--selected" : undefined}>
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
