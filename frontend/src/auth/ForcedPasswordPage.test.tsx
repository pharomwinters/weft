import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SessionInfo } from "../api/types";
import { apiError, mockApi, partial, verified, type Reply } from "../test/utils";
import ForcedPasswordPage from "./ForcedPasswordPage";
import { click, location, renderPage, typeNewPassword } from "./testing";

function setup(reply?: Reply) {
  let session: SessionInfo = partial("change_password");
  const calls = mockApi({
    "GET /auth/session": () => ({ body: session }),
    "POST /auth/password/forced": () => {
      if (reply) return reply;
      session = verified();
      return { body: { next: null } };
    },
  });
  renderPage(<ForcedPasswordPage />, "/change-password", "/change-password");
  return calls;
}

describe("ForcedPasswordPage", () => {
  it("shows field errors from details.password under the password field", async () => {
    setup(
      apiError(400, "validation", "The password is not acceptable.", {
        password: ["This password is too common."],
      }),
    );
    await typeNewPassword("password123456", undefined, "New password");
    await click("Change password");
    expect(await screen.findByText("This password is too common.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("requires the password to be typed twice and matching", async () => {
    const calls = setup();
    await typeNewPassword("a long new passphrase", "a different passphrase", "New password");
    await click("Change password");
    expect(await screen.findByText("The passwords do not match.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("sends the new password and goes home", async () => {
    const calls = setup();
    await typeNewPassword("a long new passphrase", undefined, "New password");
    await click("Change password");
    await waitFor(() => expect(location()).toBe("/"));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      new_password: "a long new passphrase",
    });
  });
});
