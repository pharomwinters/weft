import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SessionInfo } from "../api/types";
import { ANONYMOUS, apiError, mockApi, partial, type Reply } from "../test/utils";
import InvitationPage from "./InvitationPage";
import { click, location, renderPage, type, typeNewPassword } from "./testing";

const DEAD = apiError(404, "invalid_token", "This invitation is no longer valid.");
const TEAM = { body: { workspace_name: "Team", role: "viewer" } };

function setup(info: Reply, accept?: Reply) {
  let session: SessionInfo = ANONYMOUS;
  const calls = mockApi({
    "GET /auth/session": () => ({ body: session }),
    "GET /invitations/token/tok123": info,
    "POST /invitations/token/tok123/accept": () => {
      if (accept) return accept;
      session = partial("enrol");
      return { status: 201, body: { next: "enrol" } };
    },
  });
  renderPage(<InvitationPage />, "/invite/:token", "/invite/tok123");
  return calls;
}

async function fill(password = "an invited passphrase", again = password) {
  await type("Email", "new@example.com");
  await typeNewPassword(password, again);
  await click("Create account");
}

describe("InvitationPage", () => {
  it("shows the workspace name and role when the invitation carries them", async () => {
    setup(TEAM);
    expect(await screen.findByText(/workspace Team as viewer/)).toBeInTheDocument();
  });

  it("says only that an account is offered when there is no workspace", async () => {
    setup({ body: { workspace_name: null, role: null } });
    expect(await screen.findByText(/invited to create an account/)).toBeInTheDocument();
  });

  it("shows a single 'no longer valid' message for invalid_token", async () => {
    setup(DEAD);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This invitation is no longer valid.",
    );
    expect(screen.queryByLabelText(/Email/)).not.toBeInTheDocument();
  });

  it("shows the same message when the invitation dies before it is accepted", async () => {
    setup(TEAM, DEAD);
    await fill();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This invitation is no longer valid.",
    );
  });

  it("creates the account and goes to /enrol", async () => {
    const calls = setup(TEAM);
    await fill();
    await waitFor(() => expect(location()).toBe("/enrol"));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      email: "new@example.com",
      password: "an invited passphrase",
    });
  });

  it("shows field errors from details.password under the password field", async () => {
    setup(TEAM, apiError(400, "validation", "Not acceptable.", { password: ["Too short."] }));
    await fill();
    expect(await screen.findByText("Too short.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows email_taken under the email field", async () => {
    setup(TEAM, apiError(409, "email_taken", "That email address is already in use."));
    await fill();
    expect(await screen.findByText("That email address is already in use.")).toBeInTheDocument();
  });

  it("requires the password to be typed twice and matching", async () => {
    const calls = setup(TEAM);
    await fill("an invited passphrase", "not the same at all");
    expect(await screen.findByText("The passwords do not match.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});
