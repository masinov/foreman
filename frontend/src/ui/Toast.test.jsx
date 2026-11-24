import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";

import { TOAST_MS, ToastProvider, useNotice, useToast } from "./Toast";

function Trigger() {
  const { show } = useToast();
  return (
    <>
      <button type="button" onClick={() => show("Approved FOR-1.")}>
        one
      </button>
      <button type="button" onClick={() => show("Approved FOR-2.")}>
        two
      </button>
    </>
  );
}

function Noticing() {
  const [notice, setNotice] = useNotice();
  return (
    <>
      <button type="button" onClick={() => setNotice({ error: false, text: "Saved." })}>
        ok
      </button>
      <button type="button" onClick={() => setNotice({ error: true, text: "It failed." })}>
        fail
      </button>
      {notice ? (
        <p className="notice notice--error" role="alert">
          {notice.text}
        </p>
      ) : null}
    </>
  );
}

function setup(children = <Trigger />) {
  render(<ToastProvider>{children}</ToastProvider>);
}

describe("Toast", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("is a live region that is always there and says the sentence when shown", () => {
    setup();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    fireEvent.click(screen.getByText("one"));
    expect(screen.getByRole("status")).toHaveTextContent("Approved FOR-1.");
  });

  it("goes after about six seconds", () => {
    setup();
    fireEvent.click(screen.getByText("one"));
    act(() => vi.advanceTimersByTime(TOAST_MS - 100));
    expect(screen.getByRole("status")).toHaveTextContent("Approved FOR-1.");
    act(() => vi.advanceTimersByTime(200));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("is replaced by a new one, which has its own time", () => {
    setup();
    fireEvent.click(screen.getByText("one"));
    act(() => vi.advanceTimersByTime(TOAST_MS - 1000));
    fireEvent.click(screen.getByText("two"));
    expect(screen.getByRole("status")).toHaveTextContent("Approved FOR-2.");
    expect(screen.getByRole("status")).not.toHaveTextContent("FOR-1");
    act(() => vi.advanceTimersByTime(TOAST_MS - 100));
    expect(screen.getByRole("status")).toHaveTextContent("Approved FOR-2.");
  });

  it("stays while the pointer or focus is on it, then goes after its time", () => {
    setup();
    fireEvent.click(screen.getByText("one"));
    const toast = screen.getByRole("status").firstElementChild;
    fireEvent.mouseEnter(toast);
    act(() => vi.advanceTimersByTime(TOAST_MS * 3));
    expect(screen.getByRole("status")).toHaveTextContent("Approved FOR-1.");
    fireEvent.mouseLeave(toast);
    act(() => vi.advanceTimersByTime(TOAST_MS + 100));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();

    fireEvent.click(screen.getByText("one"));
    const again = screen.getByRole("status").firstElementChild;
    fireEvent.focus(screen.getByRole("button", { name: "Dismiss" }));
    act(() => vi.advanceTimersByTime(TOAST_MS * 3));
    expect(screen.getByRole("status")).toHaveTextContent("Approved FOR-1.");
    fireEvent.blur(screen.getByRole("button", { name: "Dismiss" }));
    expect(again).toBeTruthy();
  });

  it("has a close control", () => {
    setup();
    fireEvent.click(screen.getByText("one"));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("says a success in the toast and keeps an error inline", () => {
    setup(<Noticing />);
    fireEvent.click(screen.getByText("ok"));
    expect(screen.getByRole("status")).toHaveTextContent("Saved.");
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByText("fail"));
    expect(screen.getByRole("alert")).toHaveTextContent("It failed.");
    expect(screen.getByRole("status")).not.toHaveTextContent("It failed.");
    fireEvent.click(screen.getByText("ok"));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
