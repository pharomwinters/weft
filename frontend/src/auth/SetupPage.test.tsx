import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SessionInfo } from "../api/types";
import { ANONYMOUS, apiError, mockApi, partial, type Reply } from "../test/utils";
import SetupPage from "./SetupPage";
import { click, location, renderPage, type, typeNewPassword } from "./testing";

function setup(status: Reply, create?: Reply) {
  let session: SessionInfo = ANONYMOUS;
  const calls = mockApi({
    "GET /auth/session": () => ({ body: session }),
    "GET /setup/status": status,
    "POST /setup/admin": () => {
      if (create) return create;
      session = partial("enrol");
      return { status: 201, body: { next: "enrol" } };
    },
  });
  renderPage(<SetupPage />, "/setup", "/setup");
  return calls;
}

const OPEN = { body: { needs_setup: true } };

async function fill(password = "a long setup passphrase", again = password) {
  await type("Setup token", " the-token ");
  await type("Email", "root@example.com");
  await typeNewPassword(password, again);
  await click("Create admin");
}

describe("SetupPage", () => {
  it("redirects to /login when /setup/status is 404", async () => {
    setup(apiError(404, "not_found"));
    await waitFor(() => expect(location()).toBe("/login"));
    expect(screen.queryByLabelText(/Setup token/)).not.toBeInTheDocument();
  });

  it("submits token, email and password, then goes to /enrol", async () => {
    const calls = setup(OPEN);
    await fill();
    await waitFor(() => expect(location()).toBe("/enrol"));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      token: "the-token",
      email: "root@example.com",
      password: "a long setup passphrase",
    });
  });

  it("shows the server's message for a wrong token", async () => {
    setup(OPEN, apiError(401, "invalid_token", "The setup token is not valid."));
    await fill();
    expect(await screen.findByRole("alert")).toHaveTextContent("The setup token is not valid.");
  });

  it("shows field errors from details.password under the password field", async () => {
    setup(OPEN, apiError(400, "validation", "Not acceptable.", { password: ["Too common."] }));
    await fill();
    expect(await screen.findByText("Too common.")).toBeInTheDocument();
  });

  it("requires the password to be typed twice and matching", async () => {
    const calls = setup(OPEN);
    await fill("a long setup passphrase", "something else entirely");
    expect(await screen.findByText("The passwords do not match.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});
