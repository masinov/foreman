import { fireEvent, screen, within } from "@testing-library/react";

import { createFakeFetch, renderApp } from "../../testing/fakeApi";
import { projectRoutes } from "../../testing/projectFixture";
import { sprintRoutes } from "../../testing/sprintFixture";
import { minutesText, outcomeParts } from "./Outcomes";

function outcomesPayload(fields = {}) {
  return {
    project_id: "foreman",
    sprint_id: "sprint-56",
    tasks: { started: 8, merged: 8, passed_first_time: 7, passed_first_time_conflicts_aside: 7, closed_by_hand: 0, cancelled: 0, not_finished: 0 },
    send_backs: { tests: 0, review: 1, person: 0, merge_conflict: 0, other: 0 },
    people: { decisions_asked: 0, decisions_waiting: 0, median_wait_seconds: null, interventions: 0, interventions_by_kind: {} },
    cost: { total_usd: 2.9158, per_merged_task_usd: 0.3645, not_merged_usd: 0 },
    median_minutes_to_merge: 6.9,
    by_role_and_model: [
      { role: "code_reviewer", model: "claude-sonnet-5-5", runs: 9, failed_runs: 0, cost_usd: 0.5761, duration_seconds: 128.6, send_backs_caused: 1, tasks_built_merged: 0, tasks_built_passed_first_time: 0 },
      { role: "developer", model: "claude-sonnet-5-5", runs: 9, failed_runs: 1, cost_usd: 2.3397, duration_seconds: 2150.8, send_backs_caused: 0, tasks_built_merged: 8, tasks_built_passed_first_time: 7 },
    ],
    ...fields,
  };
}

const SPRINT_OUTCOMES = "GET /api/v1/projects/foreman/outcomes?sprint=sprint-56";

describe("outcome parts", () => {
  it("says the numbers short, with the rest on hover", () => {
    const parts = outcomeParts(outcomesPayload());
    expect(parts.map((part) => part.text)).toEqual([
      "7 of 8 first time",
      "1 sent back",
      "never asked you, you never stepped in",
      "$0.36 per merged task",
      "6.9 min to merge",
    ]);
    expect(parts[1].title).toBe("Sent back by review 1");
  });

  it("puts merge conflicts aside, causes and waits on hover", () => {
    const parts = outcomeParts(
      outcomesPayload({
        tasks: { started: 41, merged: 35, passed_first_time: 21, passed_first_time_conflicts_aside: 28, not_finished: 1 },
        send_backs: { tests: 2, review: 3, person: 2, merge_conflict: 15, other: 0 },
        people: { decisions_asked: 3, decisions_waiting: 1, median_wait_seconds: 840, interventions: 1 },
      }),
    );
    expect(parts.map((part) => part.text)).toEqual([
      "21 of 35 first time",
      "22 sent back",
      "asked you 3 times, you stepped in once",
      "1 not finished",
      "$0.36 per merged task",
      "6.9 min to merge",
    ]);
    expect(parts[0].title).toBe("Merged tasks never sent back; 28 leaving merge conflicts aside");
    expect(parts[1].title).toBe("Sent back by merge conflict 15, review 3, tests 2, you 2");
    expect(parts[2].title).toBe("Median wait for your decision: 14 min; 1 waiting now");
  });

  it("reads minutes the way a person says them", () => {
    expect(minutesText(0.5)).toBe("30 s");
    expect(minutesText(6.9)).toBe("6.9 min");
    expect(minutesText(42)).toBe("42 min");
    expect(minutesText(125)).toBe("2 h 5 min");
  });
});

describe("outcomes on the sprint page", () => {
  it("shows one line for the sprint, with roles and models behind a click", async () => {
    const routes = sprintRoutes();
    routes[SPRINT_OUTCOMES] = outcomesPayload();
    renderApp("/dashboard/sprints/sprint-56", createFakeFetch(routes));
    const line = await screen.findByRole("region", { name: "Outcomes" });
    expect(line).toHaveTextContent(
      "7 of 8 first time · 1 sent back · never asked you, you never stepped in · $0.36 per merged task · 6.9 min to merge",
    );
    expect(within(line).queryByRole("table")).toBeNull();

    fireEvent.click(within(line).getByRole("button", { name: "By role and model" }));
    const table = within(line).getByRole("table", { name: "By role and model" });
    const headers = within(table).getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(headers).toEqual(["Role", "Model", "Runs", "Failed", "Result", "Time", "Spend"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent(/Code reviewer.*sent back 1/);
    expect(rows[1]).toHaveTextContent(/Developer.*built 8 merged, 7 first time.*\$2\.34/);
  });

  it("shows nothing while no task in the sprint has started", async () => {
    const routes = sprintRoutes();
    routes[SPRINT_OUTCOMES] = outcomesPayload({
      tasks: { started: 0, merged: 0, passed_first_time: 0, passed_first_time_conflicts_aside: 0, not_finished: 0 },
      by_role_and_model: [],
    });
    const fetchImpl = createFakeFetch(routes);
    renderApp("/dashboard/sprints/sprint-56", fetchImpl);
    await screen.findByRole("heading", { level: 1, name: "Sprint 56: engine truthfulness" });
    await screen.findByText("State");
    expect(fetchImpl.calls.some((call) => call.url.endsWith("/outcomes?sprint=sprint-56"))).toBe(true);
    expect(screen.queryByRole("region", { name: "Outcomes" })).toBeNull();
  });
});

describe("outcomes on the project page", () => {
  it("shows the project's numbers for all sprints under the engine", async () => {
    const routes = projectRoutes();
    routes["GET /api/v1/projects/foreman/outcomes"] = outcomesPayload({
      sprint_id: null,
      tasks: { started: 41, merged: 35, passed_first_time: 21, passed_first_time_conflicts_aside: 28, closed_by_hand: 3, cancelled: 2, not_finished: 1 },
      send_backs: { tests: 2, review: 3, person: 2, merge_conflict: 15, other: 0 },
    });
    renderApp("/dashboard/projects/foreman", createFakeFetch(routes));
    const line = await screen.findByRole("region", { name: "Outcomes, all sprints" });
    expect(line).toHaveTextContent(/^All sprints21 of 35 first time · 22 sent back/);
    expect(line).toHaveTextContent("1 not finished");
  });
});
