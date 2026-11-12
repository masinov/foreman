import { render, screen, within } from "@testing-library/react";

import { Table } from "./Table";

const columns = [
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "count", header: "Count", className: "number", render: (row) => row.count },
];
const rows = [
  { id: "a", name: "Alpha", count: 1 },
  { id: "b", name: "Beta", count: 2 },
];

describe("Table", () => {
  it("renders column headers and one row per item", () => {
    render(<Table caption="Things" columns={columns} rows={rows} />);
    const table = screen.getByRole("table", { name: "Things" });
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["Name", "Count"]);
    const bodyRows = within(table).getAllByRole("row").slice(1);
    expect(bodyRows).toHaveLength(2);
    expect(within(bodyRows[1]).getByText("2")).toHaveClass("number");
    expect(table).toHaveClass("table");
    expect(table).not.toHaveClass("table--tinted");
    expect(table.parentElement).toHaveClass("table-scroll");
  });

  it("has a tinted variant and can hide its header visually", () => {
    render(<Table caption="Needs you" columns={columns} rows={rows} tinted hideHeader />);
    const table = screen.getByRole("table", { name: "Needs you" });
    expect(table).toHaveClass("table--tinted");
    // Still there for assistive technology.
    expect(within(table).getAllByRole("columnheader")).toHaveLength(2);
    expect(table.querySelector("thead")).toHaveClass("visually-hidden");
  });

  it("renders placeholder rows instead of data while asked to", () => {
    render(<Table caption="Things" columns={columns} rows={rows} placeholderRows={3} />);
    const table = screen.getByRole("table", { name: "Things" });
    expect(table).toHaveAttribute("aria-busy", "true");
    expect(table.querySelectorAll("tbody tr.table__placeholder")).toHaveLength(3);
    expect(screen.queryByText("Alpha")).toBeNull();
  });

  it("shades the row a person selected", () => {
    render(<Table caption="Things" columns={columns} rows={rows} selected={(row) => row === rows[1]} />);
    const bodyRows = screen.getByRole("table", { name: "Things" }).querySelectorAll("tbody tr");
    expect(bodyRows[0]).not.toHaveClass("table__row--selected");
    expect(bodyRows[1]).toHaveClass("table__row--selected");
  });
});
