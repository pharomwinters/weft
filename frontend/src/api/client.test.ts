import { describe, expect, it, vi } from "vitest";

import { apiError, mockApi } from "../test/utils";
import { ApiFailure, fieldErrors, onAuthRequired, request } from "./client";

describe("request", () => {
  it("sends the CSRF cookie value as X-CSRFToken on unsafe methods", async () => {
    document.cookie = "csrftoken=abc123";
    const calls = mockApi({ "POST /auth/logout": { status: 204 } });
    await request("POST", "/auth/logout");
    expect(calls[0]?.headers["X-CSRFToken"]).toBe("abc123");
  });

  it("does not send X-CSRFToken on GET", async () => {
    document.cookie = "csrftoken=abc123";
    const calls = mockApi({ "GET /health": { body: { status: "ok" } } });
    expect(await request("GET", "/health")).toEqual({ status: "ok" });
    expect(calls[0]?.headers).not.toHaveProperty("X-CSRFToken");
  });

  it("sends a JSON body under /api/v1", async () => {
    const calls = mockApi({ "POST /workspaces": { status: 201, body: { id: 1 } } });
    await request("POST", "/workspaces", { name: "Team" });
    expect(calls[0]).toMatchObject({ path: "/workspaces", body: { name: "Team" } });
    expect(calls[0]?.headers["Content-Type"]).toBe("application/json");
  });

  it("throws ApiFailure carrying status, code and details from the error body", async () => {
    mockApi({
      "POST /workspaces": apiError(400, "validation", "Not valid.", { name: ["Too long."] }),
    });
    const failure = await request("POST", "/workspaces", {}).catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiFailure);
    expect(failure).toMatchObject({
      status: 400,
      code: "validation",
      message: "Not valid.",
      details: { name: ["Too long."] },
    });
    expect(fieldErrors(failure, "name")).toEqual(["Too long."]);
    expect(fieldErrors(failure, "other")).toEqual([]);
  });

  it("throws ApiFailure with code 'network' when the response is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>Bad gateway</html>", { status: 502 })),
    );
    await expect(request("GET", "/health")).rejects.toMatchObject({
      status: 502,
      code: "network",
    });
  });

  it("throws ApiFailure with code 'network' when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(request("GET", "/health")).rejects.toMatchObject({
      status: 0,
      code: "network",
    });
  });

  it("returns undefined for 204", async () => {
    mockApi({ "DELETE /workspaces/1": { status: 204 } });
    expect(await request("DELETE", "/workspaces/1")).toBeUndefined();
  });

  it("reports auth_required to the registered handler, and no other 401", async () => {
    const handler = vi.fn();
    onAuthRequired(handler);
    mockApi({
      "GET /account": apiError(401, "auth_required", "Sign in.", {
        session: "partial",
        next: "verify",
      }),
      "POST /auth/login": apiError(401, "invalid_credentials"),
    });
    await expect(request("POST", "/auth/login", {})).rejects.toMatchObject({ status: 401 });
    expect(handler).not.toHaveBeenCalled();
    await expect(request("GET", "/account")).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledOnce();
    expect(handler.mock.calls[0]?.[0]).toMatchObject({ details: { next: "verify" } });
    onAuthRequired(null);
  });
});
