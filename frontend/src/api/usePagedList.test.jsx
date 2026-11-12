import React, { useState } from "react";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { ApiError } from "./client";
import { usePagedList } from "./usePagedList";
import { renderWithApi } from "../testing/fakeApi";

const ALL = Array.from({ length: 7 }, (_, index) => `item-${index}`);

function pager(calls, { fail = false } = {}) {
  return async (_client, { limit, offset, filter = "" }) => {
    calls.push({ limit, offset, filter });
    if (fail) throw new ApiError("Not permitted.", { code: "forbidden", status: 403 });
    const matching = ALL.filter((item) => item.includes(filter));
    return { items: matching.slice(offset, offset + limit), total: matching.length };
  };
}

function Probe({ load, pageSize = 3 }) {
  const [filter, setFilter] = useState("");
  const list = usePagedList(["things", filter], (client, options) => load(client, { ...options, filter }), {
    pageSize,
  });
  return (
    <div>
      <span data-testid="items">{list.items ? list.items.join(",") : "none"}</span>
      <span data-testid="total">{String(list.total)}</span>
      <span data-testid="error">{list.error ?? "no error"}</span>
      <span data-testid="more">{list.hasMore ? "more" : "end"}</span>
      <button type="button" onClick={() => list.loadMore()}>
        more
      </button>
      <button type="button" onClick={() => list.loadMore(10)}>
        rest
      </button>
      <button type="button" onClick={() => setFilter("6")}>
        filter
      </button>
      <button type="button" onClick={list.reload}>
        reload
      </button>
    </div>
  );
}

describe("usePagedList", () => {
  it("loads the first page and appends the next on request", async () => {
    const calls = [];
    renderWithApi(<Probe load={pager(calls)} />);
    await waitFor(() => expect(screen.getByTestId("items")).toHaveTextContent("item-0,item-1,item-2"));
    expect(screen.getByTestId("total")).toHaveTextContent("7");
    expect(screen.getByTestId("more")).toHaveTextContent("more");

    fireEvent.click(screen.getByRole("button", { name: "more" }));
    await waitFor(() => expect(screen.getByTestId("items")).toHaveTextContent("item-5"));
    fireEvent.click(screen.getByRole("button", { name: "rest" }));
    await waitFor(() => expect(screen.getByTestId("more")).toHaveTextContent("end"));
    expect(screen.getByTestId("items").textContent.split(",")).toEqual(ALL);
    expect(calls).toEqual([
      { limit: 3, offset: 0, filter: "" },
      { limit: 3, offset: 3, filter: "" },
      { limit: 10, offset: 6, filter: "" },
    ]);
  });

  it("starts again from the first page for a new key and on reload", async () => {
    const calls = [];
    renderWithApi(<Probe load={pager(calls)} />);
    await waitFor(() => expect(screen.getByTestId("items")).toHaveTextContent("item-0"));
    fireEvent.click(screen.getByRole("button", { name: "more" }));
    await waitFor(() => expect(screen.getByTestId("items")).toHaveTextContent("item-5"));

    fireEvent.click(screen.getByRole("button", { name: "filter" }));
    await waitFor(() => expect(screen.getByTestId("items")).toHaveTextContent(/^item-6$/));
    expect(screen.getByTestId("total")).toHaveTextContent("1");
    expect(calls.at(-1)).toEqual({ limit: 3, offset: 0, filter: "6" });

    fireEvent.click(screen.getByRole("button", { name: "reload" }));
    await waitFor(() => expect(calls).toHaveLength(4));
    expect(calls.at(-1)).toEqual({ limit: 3, offset: 0, filter: "6" });
  });

  it("ignores a page that answers after the key changed", async () => {
    let releaseOld;
    const load = (_client, { offset, filter }) => {
      if (filter === "" && offset === 0) {
        return new Promise((resolve) => {
          releaseOld = () => resolve({ items: ["stale"], total: 1 });
        });
      }
      return Promise.resolve({ items: ["fresh"], total: 1 });
    };
    renderWithApi(<Probe load={load} />);
    await waitFor(() => expect(releaseOld).toBeDefined());
    fireEvent.click(screen.getByRole("button", { name: "filter" }));
    await waitFor(() => expect(screen.getByTestId("items")).toHaveTextContent("fresh"));
    releaseOld();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.getByTestId("items")).toHaveTextContent("fresh");
  });

  it("reports a failure as the API's sentence", async () => {
    renderWithApi(<Probe load={pager([], { fail: true })} />);
    await waitFor(() => expect(screen.getByTestId("error")).toHaveTextContent("Not permitted."));
    expect(screen.getByTestId("items")).toHaveTextContent("none");
  });
});
