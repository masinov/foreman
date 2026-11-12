import React, { useState } from "react";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";

import { ApiError } from "./client";
import { useDelayedFlag, useResource } from "./useResource";
import { createFakeFetch, renderWithApi } from "../testing/fakeApi";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function Probe({ resourceKey, load }) {
  const { data, error, loading, reload } = useResource(resourceKey, load);
  return (
    <div>
      <span data-testid="data">{data === null ? "none" : String(data)}</span>
      <span data-testid="error">{error ?? "no error"}</span>
      <span data-testid="loading">{loading ? "loading" : "idle"}</span>
      <button type="button" onClick={reload}>
        reload
      </button>
    </div>
  );
}

function KeyedProbe({ load }) {
  const [key, setKey] = useState("a");
  return (
    <>
      <button type="button" onClick={() => setKey("b")}>
        switch
      </button>
      <Probe resourceKey={["thing", key]} load={(client, options) => load(key, options)} />
    </>
  );
}

describe("useResource", () => {
  it("returns data and stops loading", async () => {
    renderWithApi(<Probe resourceKey="x" load={async () => "hello"} />, createFakeFetch());
    expect(screen.getByTestId("loading")).toHaveTextContent("loading");
    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("hello"));
    expect(screen.getByTestId("loading")).toHaveTextContent("idle");
  });

  it("ignores a response that arrives after a newer request", async () => {
    const pending = { a: deferred(), b: deferred() };
    renderWithApi(<KeyedProbe load={(key) => pending[key].promise} />, createFakeFetch());

    fireEvent.click(screen.getByText("switch"));
    await act(async () => pending.b.resolve("from b"));
    expect(screen.getByTestId("data")).toHaveTextContent("from b");

    // The older request for "a" answers last; its answer must not win.
    await act(async () => pending.a.resolve("from a"));
    expect(screen.getByTestId("data")).toHaveTextContent("from b");
  });

  it("ignores a stale reload of the same key", async () => {
    const answers = [deferred(), deferred()];
    let calls = 0;
    renderWithApi(<Probe resourceKey="x" load={() => answers[calls++].promise} />, createFakeFetch());

    fireEvent.click(screen.getByText("reload"));
    await waitFor(() => expect(calls).toBe(2));
    await act(async () => answers[1].resolve("newer"));
    await act(async () => answers[0].resolve("older"));
    expect(screen.getByTestId("data")).toHaveTextContent("newer");
  });

  it("surfaces an API error as a sentence and keeps the last data", async () => {
    let fail = false;
    const load = async () => {
      if (fail) throw new ApiError("Project not found: p1.", { code: "not_found", status: 404 });
      return "first";
    };
    renderWithApi(<Probe resourceKey="x" load={load} />, createFakeFetch());
    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("first"));

    fail = true;
    fireEvent.click(screen.getByText("reload"));
    await waitFor(() => expect(screen.getByTestId("error")).toHaveTextContent("Project not found: p1."));
    expect(screen.getByTestId("data")).toHaveTextContent("first");
  });

  it("reloads on request", async () => {
    let count = 0;
    renderWithApi(<Probe resourceKey="x" load={async () => `call ${++count}`} />, createFakeFetch());
    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("call 1"));
    fireEvent.click(screen.getByText("reload"));
    await waitFor(() => expect(screen.getByTestId("data")).toHaveTextContent("call 2"));
  });
});

describe("useDelayedFlag", () => {
  afterEach(() => vi.useRealTimers());

  function Flag({ active }) {
    return <span data-testid="flag">{useDelayedFlag(active, 200) ? "shown" : "hidden"}</span>;
  }

  it("turns on only after the delay", () => {
    vi.useFakeTimers();
    renderWithApi(<Flag active />, createFakeFetch());
    expect(screen.getByTestId("flag")).toHaveTextContent("hidden");
    act(() => vi.advanceTimersByTime(199));
    expect(screen.getByTestId("flag")).toHaveTextContent("hidden");
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByTestId("flag")).toHaveTextContent("shown");
  });
});
