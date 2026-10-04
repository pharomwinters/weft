import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { click, renderPage, type, typeNewPassword } from "../auth/testing";
import { apiError, mockApi, verified, type Reply } from "../test/utils";
import AccountPage from "./AccountPage";

const SECRET = "JBSWY3DPEHPK3PXP";
const CODES = Array.from({ length: 10 }, (_, i) => `aaaa-bbbb-cccc-000${i}`);

function setup(overrides: Record<string, Reply | ((body: unknown) => Reply)> = {}) {
  const sessions = [
    {
      id: 1,
      ip: "203.0.113.9",
      user_agent: "Firefox on Linux",
      created: "2026-10-01T10:00:00Z",
      last_seen: "2026-10-03T10:00:00Z",
      current: true,
    },
    {
      id: 2,
      ip: "198.51.100.7",
      user_agent: "Safari on iPhone",
      created: "2026-10-02T10:00:00Z",
      last_seen: "2026-10-02T11:00:00Z",
      current: false,
    },
  ];
  const calls = mockApi({
    "GET /auth/session": { body: verified() },
    "GET /account/sessions": () => ({ body: sessions }),
    "DELETE /account/sessions/2": () => {
      sessions.pop();
      return { status: 204 };
    },
    "POST /account/password": { status: 204 },
    "POST /account/2fa/reenrol/start": {
      body: { secret: SECRET, otpauth_uri: `otpauth://totp/x?secret=${SECRET}` },
    },
    "POST /account/2fa/reenrol/confirm": { body: { recovery_codes: CODES } },
    ...overrides,
  });
  renderPage(<AccountPage />, "/account", "/account");
  return calls;
}

describe("AccountPage", () => {
  it("lists sessions and marks the current one", async () => {
    setup();
    const current = (await screen.findByText("Firefox on Linux")).closest("tr")!;
    expect(within(current).getByText("This session")).toBeInTheDocument();
    expect(within(current).queryByRole("button")).not.toBeInTheDocument();
    const other = screen.getByText("Safari on iPhone").closest("tr")!;
    expect(within(other).getByText("198.51.100.7")).toBeInTheDocument();
    expect(within(other).getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("revokes another session", async () => {
    const calls = setup();
    const other = (await screen.findByText("Safari on iPhone")).closest("tr")!;
    await userEvent.click(within(other).getByRole("button", { name: "Sign out" }));
    expect(await screen.findByText("Firefox on Linux")).toBeInTheDocument();
    await screen.findByText("This session");
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/account/sessions/2")).toBe(
      true,
    );
  });

  it("changes the password with the current one", async () => {
    const calls = setup();
    await type("Current password", "correct horse battery");
    await typeNewPassword("a brand new passphrase", undefined, "New password");
    await click("Change password");
    expect(await screen.findByRole("status")).toHaveTextContent("Password changed");
    expect(calls.find((c) => c.path === "/account/password")?.body).toEqual({
      current_password: "correct horse battery",
      new_password: "a brand new passphrase",
    });
  });

  it("shows field errors from details.password and the wrong-password message", async () => {
    setup({
      "POST /account/password": apiError(400, "validation", "Not acceptable.", {
        password: ["The new password must differ from the current one."],
      }),
    });
    await type("Current password", "correct horse battery");
    await typeNewPassword("correct horse battery", undefined, "New password");
    await click("Change password");
    expect(await screen.findByText(/must differ from the current one/)).toBeInTheDocument();
  });

  it("asks for a current code before starting re-enrolment", async () => {
    const calls = setup();
    await screen.findByText("Firefox on Linux");
    expect(screen.queryByTitle("Authenticator QR code")).not.toBeInTheDocument();
    expect(calls.some((c) => c.path.startsWith("/account/2fa"))).toBe(false);

    await type("Current authentication or recovery code", "123456");
    await click("Set up a new authenticator");
    expect(await screen.findByTitle("Authenticator QR code")).toBeInTheDocument();
    expect(screen.getByLabelText("Secret key")).toHaveTextContent(SECRET);
    expect(calls.find((c) => c.path === "/account/2fa/reenrol/start")?.body).toEqual({
      code: "123456",
    });

    await type("Code from the new authenticator", "654 321");
    await click("Confirm new authenticator");
    expect(await screen.findByText(CODES[0]!)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/account/2fa/reenrol/confirm")?.body).toEqual({
      code: "654321",
    });
  });

  it("shows the server's message when the current code is wrong", async () => {
    setup({
      "POST /account/2fa/reenrol/start": apiError(401, "invalid_code", "That code is not valid."),
    });
    await type("Current authentication or recovery code", "000000");
    await click("Set up a new authenticator");
    expect(await screen.findByRole("alert")).toHaveTextContent("That code is not valid.");
    expect(screen.queryByTitle("Authenticator QR code")).not.toBeInTheDocument();
  });
});
