import React, { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { Dialog } from "./Dialog";

function Harness({ onClose = () => {} }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <Dialog
        open={open}
        title="New sprint"
        description="It joins the end of the queue."
        onClose={() => {
          onClose();
          setOpen(false);
        }}
        footer={
          <>
            <button type="button" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button type="button">Create</button>
          </>
        }
      >
        <label htmlFor="t">Title</label>
        <input id="t" data-autofocus />
      </Dialog>
    </>
  );
}

describe("Dialog", () => {
  it("is a labelled modal dialog that starts focus on the marked element", () => {
    render(<Harness />);
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    const dialog = screen.getByRole("dialog", { name: "New sprint" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription("It joins the end of the queue.");
    expect(screen.getByLabelText("Title")).toHaveFocus();
  });

  it("keeps Tab and Shift+Tab inside", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    const dialog = screen.getByRole("dialog");
    const create = screen.getByRole("button", { name: "Create" });
    const title = screen.getByLabelText("Title");

    create.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(title).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(create).toHaveFocus();
  });

  it("closes on Escape and gives focus back to what opened it", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const opener = screen.getByRole("button", { name: "Open" });
    opener.focus();
    fireEvent.click(opener);
    fireEvent.keyDown(screen.getByLabelText("Title"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });
});
