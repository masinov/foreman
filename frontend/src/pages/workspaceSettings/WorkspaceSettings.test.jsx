import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { createFakeFetch, renderApp, reply } from "../../testing/fakeApi";
import { accessRoutes, CHANNEL, MACHINE, ROLES, RUNNERS, TOKEN } from "../../testing/accessFixture";

function section(name) {
  return screen.getByRole("region", { name });
}

async function openPage(routes = accessRoutes()) {
  const fetchImpl = createFakeFetch(routes);
  renderApp("/dashboard/settings", fetchImpl);
  await screen.findByRole("table", { name: "Workflows" });
  await screen.findByRole("table", { name: "API tokens" });
  return fetchImpl;
}

describe("Workspace settings", () => {
  it("renders the five sections from the server and puts Workspace / Settings in the breadcrumb", async () => {
    await openPage();
    expect(screen.getByRole("heading", { name: "Workspace settings", level: 1 })).toBeInTheDocument();
    expect(
      screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent),
    ).toEqual(["Defaults for projects", "Access", "Notification channels", "Runners", "This machine"]);
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByRole("link", { name: "Workspace" })).toHaveAttribute("href", "/dashboard");
    expect(within(crumbs).getByText("Settings")).toHaveAttribute("aria-current", "page");
    expect(document.title).toBe("Workspace settings · Foreman");
  });

  describe("defaults for projects", () => {
    it("lists workflows with the projects that use each, and the roles, with no create buttons", async () => {
      await openPage();
      const defaults = section("Defaults for projects");
      const workflows = within(within(defaults).getByRole("table", { name: "Workflows" }));
      const development = workflows.getByText("development").closest("tr");
      expect(within(development).getByText("Foreman, Other project")).toBeInTheDocument();
      const light = workflows.getByText("light").closest("tr");
      expect(within(light).getByText("No project")).toBeInTheDocument();
      const roles = within(within(defaults).getByRole("table", { name: "Roles" }));
      expect(roles.getByText("developer")).toBeInTheDocument();
      expect(roles.getByText("code_reviewer")).toBeInTheDocument();
      expect(within(defaults).queryByRole("button", { name: /new (workflow|role)/i })).toBeNull();
    });

    it("opens a role read-only with the file it comes from", async () => {
      await openPage();
      fireEvent.click(screen.getByRole("button", { name: "Open role code_reviewer" }));
      const dialog = screen.getByRole("dialog", { name: "Code Reviewer" });
      expect(within(dialog).getByText(/Reviews completed work/)).toBeInTheDocument();
      expect(within(dialog).getByText("claude-sonnet-5-5")).toBeInTheDocument();
      expect(within(dialog).getByText("30 minutes")).toBeInTheDocument();
      expect(within(dialog).getByText(ROLES[1].source_path)).toBeInTheDocument();
      expect(within(dialog).queryByRole("textbox")).toBeNull();
      fireEvent.keyDown(dialog, { key: "Escape" });
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("opens a workflow read-only with its steps and its file", async () => {
      await openPage();
      fireEvent.click(screen.getByRole("button", { name: "Open workflow development" }));
      const dialog = screen.getByRole("dialog", { name: "Standard Development" });
      const steps = within(dialog).getByRole("table", { name: "Steps of Standard Development" });
      expect(within(steps).getByText("Merge approval")).toBeInTheDocument();
      expect(within(dialog).getByText("/srv/foreman/foreman/data/workflows/development.toml")).toBeInTheDocument();
    });
  });

  describe("access", () => {
    it("lists tokens with scopes, dates and last use, and says who identifies people when no provider is set", async () => {
      await openPage();
      const access = section("Access");
      const tokens = within(within(access).getByRole("table", { name: "API tokens" }));
      const row = tokens.getByText("pagerduty").closest("tr");
      expect(within(row).getByText("intake")).toBeInTheDocument();
      expect(within(row).getByText("1 Nov")).toBeInTheDocument();
      expect(within(row).getByText("10 Nov")).toBeInTheDocument();
      expect(within(row).getByRole("button", { name: "Revoke pagerduty" })).toBeInTheDocument();
      const revoked = tokens.getByText("old-ci").closest("tr");
      expect(within(revoked).getByText("Never")).toBeInTheDocument();
      expect(within(revoked).getByText("Revoked 5 Nov")).toBeInTheDocument();
      expect(within(revoked).queryByRole("button", { name: /Revoke/ })).toBeNull();
      await waitFor(() =>
        expect(within(access).getByText(/Identity provider: none configured/)).toBeInTheDocument(),
      );
      expect(within(access).getByText(/identified by the token they use/)).toBeInTheDocument();
    });

    it("says so when there are no tokens", async () => {
      renderApp("/dashboard/settings", createFakeFetch(accessRoutes({ tokens: [] })));
      expect(await screen.findByText(/No tokens yet/)).toBeInTheDocument();
    });

    it("creates a token, shows the secret once with a copy button, and reloads the list", async () => {
      const writeText = vi.fn().mockResolvedValue();
      Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
      const secret = "fmn_the-only-time-you-see-this";
      let created = false;
      const routes = accessRoutes();
      routes["GET /api/v1/tokens"] = () => ({
        tokens: created ? [{ ...TOKEN, id: "tok-2", name: "ci" }, TOKEN] : [TOKEN],
        scopes: ["intake"],
      });
      routes["POST /api/v1/projects/foreman/tokens"] = () => {
        created = true;
        return { ...TOKEN, id: "tok-2", name: "ci", secret };
      };
      const fetchImpl = await openPage(routes);

      fireEvent.click(screen.getByRole("button", { name: "New token" }));
      const form = screen.getByRole("dialog", { name: "New token" });
      fireEvent.click(within(form).getByRole("button", { name: "Create token" }));
      expect(within(form).getByText("A token needs a name.")).toBeInTheDocument();
      fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "ci" } });
      fireEvent.click(within(form).getByRole("button", { name: "Create token" }));

      const shown = await screen.findByRole("dialog", { name: "Copy the secret now" });
      expect(within(shown).getByText(secret)).toBeInTheDocument();
      expect(fetchImpl.calls.find((call) => call.method === "POST").body).toEqual({ name: "ci", scopes: ["intake"] });
      fireEvent.click(within(shown).getByRole("button", { name: "Copy secret" }));
      await waitFor(() => expect(writeText).toHaveBeenCalledWith(secret));
      expect(await within(shown).findByRole("button", { name: "Copied" })).toBeInTheDocument();

      // The list reloaded and shows the new token; closing drops the secret for good.
      expect(await screen.findByText("ci")).toBeInTheDocument();
      fireEvent.click(within(shown).getByRole("button", { name: "Done" }));
      expect(screen.queryByText(secret)).toBeNull();
      expect(document.body.textContent).not.toContain(secret);
      expect(fetchImpl.calls.filter((call) => call.url === "/api/v1/tokens")).toHaveLength(2);
    });

    it("says when the browser will not copy", async () => {
      Object.defineProperty(navigator, "clipboard", {
        value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
        configurable: true,
      });
      const routes = accessRoutes();
      routes["POST /api/v1/projects/foreman/tokens"] = { ...TOKEN, secret: "fmn_x" };
      await openPage(routes);
      fireEvent.click(screen.getByRole("button", { name: "New token" }));
      fireEvent.change(screen.getByLabelText("Name"), { target: { value: "ci" } });
      fireEvent.click(screen.getByRole("button", { name: "Create token" }));
      fireEvent.click(await screen.findByRole("button", { name: "Copy secret" }));
      expect(await screen.findByText(/would not copy/)).toBeInTheDocument();
    });

    it("shows the API's refusal beside the field", async () => {
      const routes = accessRoutes();
      routes["POST /api/v1/projects/foreman/tokens"] = reply(400, {
        error: "An API token needs a name.",
        code: "invalid_request",
        field: "name",
      });
      await openPage(routes);
      fireEvent.click(screen.getByRole("button", { name: "New token" }));
      fireEvent.change(screen.getByLabelText("Name"), { target: { value: "ci" } });
      fireEvent.click(screen.getByRole("button", { name: "Create token" }));
      expect(await screen.findByText("An API token needs a name.")).toBeInTheDocument();
      expect(screen.queryByRole("dialog", { name: "Copy the secret now" })).toBeNull();
    });

    it("asks before revoking, then revokes through the API and reloads", async () => {
      let revoked = false;
      const routes = accessRoutes();
      routes["GET /api/v1/tokens"] = () => ({
        tokens: [revoked ? { ...TOKEN, active: false, revoked_at: "2026-11-11T09:00:00Z" } : TOKEN],
        scopes: ["intake"],
      });
      routes["POST /api/v1/tokens/tok-1/revoke"] = () => {
        revoked = true;
        return { ...TOKEN, active: false };
      };
      const fetchImpl = await openPage(routes);

      fireEvent.click(screen.getByRole("button", { name: "Revoke pagerduty" }));
      const confirm = screen.getByRole("dialog", { name: "Revoke pagerduty?" });
      expect(fetchImpl.calls.some((call) => call.method === "POST")).toBe(false);
      fireEvent.click(within(confirm).getByRole("button", { name: "Cancel" }));
      expect(fetchImpl.calls.some((call) => call.method === "POST")).toBe(false);

      fireEvent.click(screen.getByRole("button", { name: "Revoke pagerduty" }));
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Revoke token" }));
      expect(await screen.findByText("Revoked 11 Nov")).toBeInTheDocument();
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(fetchImpl.calls.filter((call) => call.method === "POST").map((call) => call.url)).toEqual([
        "/api/v1/tokens/tok-1/revoke",
      ]);
    });

    it("keeps the confirmation open and says why when revoking fails", async () => {
      const routes = accessRoutes();
      routes["POST /api/v1/tokens/tok-1/revoke"] = reply(404, { error: "API token not found: tok-1", code: "not_found" });
      await openPage(routes);
      fireEvent.click(screen.getByRole("button", { name: "Revoke pagerduty" }));
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Revoke token" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("API token not found: tok-1.");
      expect(screen.getByRole("dialog", { name: "Revoke pagerduty?" })).toBeInTheDocument();
    });
  });

  describe("notification channels", () => {
    it("says so when there are none", async () => {
      renderApp("/dashboard/settings", createFakeFetch(accessRoutes({ channels: [] })));
      expect(await screen.findByText(/No channels yet/)).toBeInTheDocument();
      expect(screen.getByText(/each project chooses what to send/)).toBeInTheDocument();
    });

    it("lists channels without exposing the signing variable", async () => {
      await openPage();
      const channels = await waitFor(() => {
        const found = section("Notification channels");
        within(found).getByText("ops-channel");
        return found;
      });
      const row = within(channels).getByText("ops-channel").closest("tr");
      expect(within(row).getByText(CHANNEL.target)).toBeInTheDocument();
      expect(within(row).getByText(/signed/)).toBeInTheDocument();
      expect(within(row).getByText("Webhook")).toBeInTheDocument();
    });

    it("adds a channel to a project and reloads", async () => {
      let added = false;
      const routes = accessRoutes({ channels: [] });
      routes["GET /api/v1/notification-channels"] = () => ({ channels: added ? [CHANNEL] : [], kinds: ["webhook"] });
      routes["POST /api/v1/projects/other/notification-channels"] = () => {
        added = true;
        return CHANNEL;
      };
      const fetchImpl = await openPage(routes);
      await screen.findByText(/No channels yet/);

      fireEvent.click(screen.getByRole("button", { name: "Add channel" }));
      const form = await screen.findByRole("dialog", { name: "Add channel" });
      fireEvent.click(within(form).getByRole("button", { name: "Add channel" }));
      expect(within(form).getByText("A channel needs a name.")).toBeInTheDocument();
      expect(within(form).getByText("A channel needs an address.")).toBeInTheDocument();
      fireEvent.change(within(form).getByLabelText("Project"), { target: { value: "other" } });
      fireEvent.change(within(form).getByLabelText("Name"), { target: { value: "ops-channel" } });
      fireEvent.change(within(form).getByLabelText("Address"), { target: { value: CHANNEL.target } });
      fireEvent.change(within(form).getByLabelText("Signing key variable"), { target: { value: "OPS_KEY" } });
      fireEvent.click(within(form).getByRole("button", { name: "Add channel" }));

      expect(await screen.findByText(CHANNEL.target)).toBeInTheDocument();
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(fetchImpl.calls.find((call) => call.method === "POST").body).toEqual({
        name: "ops-channel",
        url: CHANNEL.target,
        secret_env: "OPS_KEY",
      });
    });

    it("shows the API's refusal of an address beside the field", async () => {
      const routes = accessRoutes({ channels: [] });
      routes["POST /api/v1/projects/foreman/notification-channels"] = reply(400, {
        error: "A webhook destination needs an http:// or https:// URL, got 'ftp://x'.",
        code: "invalid_request",
        field: "url",
      });
      await openPage(routes);
      fireEvent.click(screen.getByRole("button", { name: "Add channel" }));
      fireEvent.change(screen.getByLabelText("Name"), { target: { value: "x" } });
      fireEvent.change(screen.getByLabelText("Address"), { target: { value: "ftp://x" } });
      fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Add channel" }));
      expect(await screen.findByText(/needs an http:\/\/ or https:\/\/ URL/)).toBeInTheDocument();
    });

    it("asks before removing, then removes through the API and reloads", async () => {
      let removed = false;
      const routes = accessRoutes();
      routes["GET /api/v1/notification-channels"] = () => ({ channels: removed ? [] : [CHANNEL], kinds: ["webhook"] });
      routes["DELETE /api/v1/notification-channels/dst-1"] = () => {
        removed = true;
        return { id: "dst-1", removed: true };
      };
      const fetchImpl = await openPage(routes);
      fireEvent.click(await screen.findByRole("button", { name: "Remove ops-channel" }));
      const confirm = screen.getByRole("dialog", { name: "Remove ops-channel?" });
      expect(fetchImpl.calls.some((call) => call.method === "DELETE")).toBe(false);
      fireEvent.click(within(confirm).getByRole("button", { name: "Remove channel" }));
      expect(await screen.findByText(/No channels yet/)).toBeInTheDocument();
    });
  });

  describe("runners and this machine", () => {
    it("shows what the server found, and the models roles ask for", async () => {
      await openPage();
      const runners = await waitFor(() => {
        const found = section("Runners");
        within(found).getByText("Claude Code");
        return found;
      });
      const claude = within(runners).getByText("Claude Code").closest("tr");
      expect(within(claude).getByText("Found")).toBeInTheDocument();
      expect(within(claude).getByText(RUNNERS[0].path)).toBeInTheDocument();
      expect(within(claude).getByText("claude-sonnet-5-5")).toBeInTheDocument();
      expect(within(claude).getByText(/its own default/)).toBeInTheDocument();
      const codex = within(runners).getByText("Codex").closest("tr");
      expect(within(codex).getByText("Not found")).toBeInTheDocument();
      expect(within(codex).getByText(/no codex on the path/)).toBeInTheDocument();
      expect(within(codex).getByText("None named")).toBeInTheDocument();
    });

    it("shows the database, version and address the server reports", async () => {
      const fetchImpl = await openPage();
      const machine = await waitFor(() => {
        const found = section("This machine");
        within(found).getByText(MACHINE.database_path);
        return found;
      });
      expect(within(machine).getByText(MACHINE.version)).toBeInTheDocument();
      expect(within(machine).getByText(MACHINE.address)).toBeInTheDocument();
      expect(within(machine).queryByRole("button")).toBeNull();
      const urls = fetchImpl.calls.map((call) => call.url);
      expect(urls).toEqual(expect.arrayContaining(["/api/v1/runners", "/api/v1/machine"]));
    });

    it("says why a section is empty when the server cannot answer", async () => {
      const routes = accessRoutes();
      routes["GET /api/v1/runners"] = reply(500, { error: "Internal error. See the dashboard log.", code: "internal_error" });
      await openPage(routes);
      expect(await screen.findByText("Internal error. See the dashboard log.")).toBeInTheDocument();
    });
  });
});
