import { fireEvent, screen, within } from "@testing-library/react";

import { createFakeFetch, renderApp } from "../../testing/fakeApi";
import { projectRoutes } from "../../testing/projectFixture";
import { sprintRoutes } from "../../testing/sprintFixture";
import { firstTimeText, minutesText, sentBackText, youText } from "./Outcomes";

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

describe("outcome sentences", () => {
  it("says how many merged tasks passed first time, and leaving conflicts aside only when it differs", () => {
    expect(firstTimeText({ merged: 8, passed_first_time: 7, passed_first_time_conflicts_aside: 7 })).toBe("7 of 8");
    expect(firstTimeText({ merged: 35, passed_first_time: 21, passed_first_time_conflicts_aside: 28 })).toBe(
      "21 of 35 (28 leaving merge conflicts aside)",
    );
  });

  it("lists send-backs by cause, largest first, and a person as you", () => {
    expect(sentBackText({ tests: 0, review: 0, person: 0, merge_conflict: 0, other: 0 })).toBe("None");
    expect(sentBackText({ tests: 2, review: 3, person: 2, merge_conflict: 15, other: 0 })).toBe(
      "22: merge conflict 15, review 3, tests 2, you 2",
    );
  });

  it("says what the person was asked and did", () => {
    expect(youText({ decisions_asked: 0, decisions_waiting: 0, interventions: 0 })).toBe("Never asked, never stepped in");
    expect(youText({ decisions_asked: 3, decisions_waiting: 1, median_wait_seconds: 840, interventions: 1 })).toBe(
      "Asked 3 times (median wait 14 min), 1 waiting, stepped in once",
    );
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
    expect(line).toHaveTextContent(/First time\s*7 of 8/);
    expect(line).toHaveTextContent(/Sent back\s*1: review 1/);
    expect(line).toHaveTextContent(/You\s*Never asked, never stepped in/);
    expect(line).toHaveTextContent(/Per merged task\s*\$0\.36/);
    expect(line).toHaveTextContent(/To merge\s*6\.9 min median/);
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
    expect(line).toHaveTextContent(/^All sprints/);
    expect(line).toHaveTextContent(/First time\s*21 of 35 \(28 leaving merge conflicts aside\)/);
    expect(line).toHaveTextContent(/Sent back\s*22: merge conflict 15, review 3, tests 2, you 2/);
    expect(line).toHaveTextContent(/Not finished\s*1 task/);
  });
});
