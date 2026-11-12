import "@testing-library/jest-dom/vitest";

// jsdom does not implement scrolling; navigation scrolls to the top.
if (typeof window !== "undefined") {
  window.scrollTo = () => {};
}
