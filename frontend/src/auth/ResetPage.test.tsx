import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ANONYMOUS, apiError, mockApi, type Reply } from "../test/utils";
import ResetPage from "./ResetPage";
import { click, renderPage, typeNewPassword } from "./testing";

const DEAD = apiError(404, "invalid_token", "This reset link is no longer valid.");

function setup(inspect: Reply, redeem: Reply = { status: 204 }) {
  const calls = mockApi({
    "GET /auth/session": { body: ANONYMOUS },
    "GET /auth/reset/tok123": inspect,
    "POST /auth/reset/tok123": redeem,
  });
  renderPage(<ResetPage />, "/reset/:token", "/reset/tok123");
  return calls;
}

async function fill(password = "a freshly reset passphrase", again = password) {
  await typeNewPassword(password, again, "New password");
  await click("Change password");
}

describe("ResetPage", () => {
  it("shows a single 'no longer valid' message for invalid_token", async () => {
    setup(DEAD);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This reset link is no longer valid.",
    );
    expect(screen.queryByLabelText(/New password/)).not.toBeInTheDocument();
  });

  it("sets the password and says the second factor is still needed", async () => {
    const calls = setup({ status: 204 });
    await fill();
    expect(await screen.findByText(/still need your authenticator code/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({
      new_password: "a freshly reset passphrase",
    });
  });

  it("shows field errors from details.password under the password field", async () => {
    setup(
      { status: 204 },
      apiError(400, "validation", "Not acceptable.", { password: ["Too similar to the email."] }),
    );
    await fill();
    expect(await screen.findByText("Too similar to the email.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("requires the password to be typed twice and matching", async () => {
    const calls = setup({ status: 204 });
    await fill("a freshly reset passphrase", "something different here");
    expect(await screen.findByText("The passwords do not match.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});
