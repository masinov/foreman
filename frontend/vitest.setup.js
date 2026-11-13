import "@testing-library/jest-dom/vitest";

// jsdom does not implement scrolling; navigation scrolls to the top.
if (typeof window !== "undefined") {
  window.scrollTo = () => {};
}

// The suite runs its files in parallel; on a busy machine a page that needs
// several requests can take longer than Testing Library's default second to
// settle, which showed up as one settings test failing now and then. Waiting
// longer costs nothing when the thing arrives on time.
import { configure } from "@testing-library/react";

configure({ asyncUtilTimeout: 4000 });
