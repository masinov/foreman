import React, { useRef } from "react";
import { render, screen } from "@testing-library/react";

import { useLinesBeside } from "./useLinesBeside";

// jsdom lays nothing out: each box is given its place by hand.
function place(element, { top, height }) {
  element.getBoundingClientRect = () => ({ top, height, bottom: top + height, left: 0, right: 0, width: 0, x: 0, y: top });
}

function Columns({ asideTop = 0 }) {
  const main = useRef(null);
  const aside = useRef(null);
  const lines = useLinesBeside(main, aside);
  return (
    <div>
      <section
        ref={(node) => {
          main.current = node;
          if (node) place(node, { top: 100, height: 200 });
        }}
      >
        <h2>Goal</h2>
        <div
          className="long-text__text"
          style={{ lineHeight: "20px" }}
          ref={(node) => {
            if (node) place(node, { top: 140, height: 80 });
          }}
        />
      </section>
      <aside
        ref={(node) => {
          aside.current = node;
          if (node) place(node, { top: 100 + asideTop, height: 300 });
        }}
      />
      <output>{lines === null ? "own fold" : lines}</output>
    </div>
  );
}

describe("how many lines fit beside a column", () => {
  it("fills the aside's height, less the text's heading and its Show all", () => {
    render(<Columns />);
    // 300 high, the text starts 40 down, 30 kept for "Show all": 230 / 20 = 11 lines.
    expect(screen.getByRole("status")).toHaveTextContent("11");
  });

  it("leaves the text its own fold when the columns are stacked", () => {
    render(<Columns asideTop={400} />);
    expect(screen.getByRole("status")).toHaveTextContent("own fold");
  });
});
