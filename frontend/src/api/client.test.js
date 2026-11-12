import { ApiError, createApiClient, errorSentence } from "./client";
import { createFakeFetch, reply } from "../testing/fakeApi";

describe("the /api/v1 client", () => {
  it("prefixes /api/v1, sends the token and returns the JSON body", async () => {
    const seen = [];
    const fetchImpl = async (url, init) => {
      seen.push({ url, init });
      return new Response(JSON.stringify({ projects: [] }), { status: 200 });
    };
    const client = createApiClient({ fetchImpl, tokenProvider: () => "secret" });
    await expect(client.get("/projects")).resolves.toEqual({ projects: [] });
    expect(seen[0].url).toBe("/api/v1/projects");
    expect(seen[0].init.headers.Authorization).toBe("Bearer secret");
  });

  it("sends a JSON body on POST", async () => {
    const fetchImpl = createFakeFetch({ "POST /api/v1/things": { ok: true } });
    const client = createApiClient({ fetchImpl, tokenProvider: () => "" });
    await client.post("/things", { a: 1 });
    expect(fetchImpl.calls[0]).toEqual({ method: "POST", url: "/api/v1/things", body: { a: 1 } });
  });

  it("turns the error envelope into an ApiError carrying its sentence and code", async () => {
    const fetchImpl = createFakeFetch({
      "GET /api/v1/projects": reply(403, { error: "Not permitted from this origin", code: "forbidden" }),
    });
    const client = createApiClient({ fetchImpl, tokenProvider: () => "" });
    const error = await client.get("/projects").catch((caught) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe("Not permitted from this origin.");
    expect(error.code).toBe("forbidden");
    expect(error.status).toBe(403);
  });

  it("says so when an error has no envelope", async () => {
    const fetchImpl = async () => new Response("<html>bad gateway</html>", { status: 502 });
    const client = createApiClient({ fetchImpl, tokenProvider: () => "" });
    const error = await client.get("/projects").catch((caught) => caught);
    expect(error.message).toBe("Foreman answered 502 without saying why.");
  });

  it("says so when the server cannot be reached", async () => {
    const fetchImpl = async () => {
      throw new TypeError("Failed to fetch");
    };
    const client = createApiClient({ fetchImpl, tokenProvider: () => "" });
    const error = await client.get("/projects").catch((caught) => caught);
    expect(error.code).toBe("network_error");
    expect(errorSentence(error)).toMatch(/could not reach Foreman/);
  });

  it("makes any error a sentence", () => {
    expect(errorSentence(new Error("boom"))).toBe("boom.");
    expect(errorSentence(null)).toBe("Something went wrong.");
  });
});
