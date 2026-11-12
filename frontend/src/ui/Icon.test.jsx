import React from "react";
import { render } from "@testing-library/react";
import { Icon, ICON_NAMES } from "./Icon";

describe("Icon", () => {
  it("draws every icon in the set, hidden from assistive technology", () => {
    for (const name of ICON_NAMES) {
      const { container, unmount } = render(<Icon name={name} />);
      const svg = container.querySelector("svg.icon");
      expect(svg).not.toBeNull();
      expect(svg).toHaveAttribute("aria-hidden", "true");
      unmount();
    }
  });

  it("renders nothing for a name it does not know", () => {
    const { container } = render(<Icon name="no-such-icon" />);
    expect(container).toBeEmptyDOMElement();
  });
});
