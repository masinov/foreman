import { fireEvent, render, screen, within } from "@testing-library/react";

import { Link, RouterProvider } from "../app/router";

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

  it("shades the row a user selected", () => {
    render(<Table caption="Things" columns={columns} rows={rows} selected={(row) => row === rows[1]} />);
    const bodyRows = screen.getByRole("table", { name: "Things" }).querySelectorAll("tbody tr");
    expect(bodyRows[0]).not.toHaveClass("table__row--selected");
    expect(bodyRows[1]).toHaveClass("table__row--selected");
  });

  it("leads the whole row to its page, but leaves a control in it to do its own job", () => {
    window.history.replaceState({}, "", "/dashboard");
    const pressed = vi.fn();
    const linked = [
      { key: "name", header: "Name", render: (row) => <Link href={`/dashboard/things/${row.id}`}>{row.name}</Link> },
      { key: "act", header: "Act", render: () => <button type="button" onClick={pressed}>Act</button> },
      { key: "count", header: "Count", render: (row) => row.count },
    ];
    render(
      <RouterProvider browser={window}>
        <Table caption="Things" columns={linked} rows={rows} rowHref={(row) => (row.id === "a" ? `/dashboard/things/${row.id}` : null)} />
      </RouterProvider>,
    );
    const [first, second] = within(screen.getByRole("table", { name: "Things" })).getAllByRole("row").slice(1);
    expect(first).toHaveClass("table__row--pickable");
    expect(second).not.toHaveClass("table__row--pickable");

    fireEvent.click(within(first).getByRole("button", { name: "Act" }));
    expect(pressed).toHaveBeenCalledTimes(1);
    expect(window.location.pathname).toBe("/dashboard");

    fireEvent.click(within(second).getByText("2"));
    expect(window.location.pathname).toBe("/dashboard");

    fireEvent.click(within(first).getByText("1"));
    expect(window.location.pathname).toBe("/dashboard/things/a");
  });
});

