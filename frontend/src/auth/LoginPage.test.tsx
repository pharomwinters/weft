import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SessionInfo } from "../api/types";
import { ANONYMOUS, apiError, mockApi, partial, type Reply } from "../test/utils";
import LoginPage from "./LoginPage";
import { click, location, renderPage, type } from "./testing";

function setup(login: Reply | (() => Reply), setupStatus: Reply = apiError(404, "not_found")) {
  let session: SessionInfo = ANONYMOUS;
  const calls = mockApi({
    "GET /auth/session": () => ({ body: session }),
    "GET /setup/status": setupStatus,
    "POST /auth/login": () => {
      const reply = typeof login === "function" ? login() : login;
      if ((reply.status ?? 200) === 200) {
        session = partial((reply.body as { next: string }).next);
      }
      return reply;
    },
  });
  renderPage(<LoginPage />, "/login", "/login");
  return calls;
}

async function signIn() {
  await type("Email", "a@example.com");
  await type("Password", "correct horse battery");
  await click("Sign in");
}

describe("LoginPage", () => {
  it("shows one generic message for invalid_credentials", async () => {
    setup(apiError(401, "invalid_credentials", "Server wording that may change."));
    await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(location()).toBe("/login");
  });

  it("shows a wait message for 429 locked", async () => {
    setup(apiError(429, "locked", "Too many attempts."));
    await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent(/wait 15 minutes/i);
  });

  it.each([
    ["verify", "/verify"],
    ["enrol", "/enrol"],
  ])("navigates by the returned next step (%s)", async (next, path) => {
    const calls = setup({ body: { next } });
    await signIn();
    await waitFor(() => expect(location()).toBe(path));
    expect(calls.find((c) => c.path === "/auth/login")?.body).toEqual({
      email: "a@example.com",
      password: "correct horse battery",
    });
  });

  it("goes to /setup while the instance has no admin", async () => {
    setup({ body: { next: "verify" } }, { body: { needs_setup: true } });
    await waitFor(() => expect(location()).toBe("/setup"));
  });
});
