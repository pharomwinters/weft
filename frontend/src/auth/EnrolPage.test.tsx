import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { SessionInfo } from "../api/types";
import { apiError, mockApi, partial, verified, type Reply } from "../test/utils";
import EnrolPage from "./EnrolPage";
import { click, location, renderPage, type } from "./testing";

const SECRET = "JBSWY3DPEHPK3PXP";
const URI = `otpauth://totp/Weft:u%40example.com?secret=${SECRET}&issuer=Weft`;
const CODES = Array.from({ length: 10 }, (_, i) => `aaaa-bbbb-cccc-000${i}`);

function setup(confirm?: Reply) {
  let session: SessionInfo = partial("enrol");
  const calls = mockApi({
    "GET /auth/session": () => ({ body: session }),
    "POST /auth/enrol/start": { body: { secret: SECRET, otpauth_uri: URI } },
    "POST /auth/enrol/confirm": () => {
      if (confirm) return confirm;
      session = verified();
      return { body: { recovery_codes: CODES, next: null } };
    },
  });
  renderPage(<EnrolPage />, "/enrol", "/enrol");
  return calls;
}

describe("EnrolPage", () => {
  it("renders the QR code and the secret as selectable text", async () => {
    const calls = setup();
    expect(await screen.findByTitle("Authenticator QR code")).toBeInTheDocument();
    const secret = screen.getByLabelText("Secret key");
    expect(secret).toHaveTextContent(SECRET);
    expect(secret).toHaveStyle({ userSelect: "all" });
    expect(calls.filter((c) => c.path === "/auth/enrol/start")).toHaveLength(1);
  });

  it("shows recovery codes after confirmation", async () => {
    const calls = setup();
    await type("Authentication code", "123 456");
    await click("Confirm");
    for (const code of CODES) expect(await screen.findByText(code)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/auth/enrol/confirm")?.body).toEqual({
      code: "123456",
    });
    expect(location()).toBe("/enrol"); // stays until the codes are acknowledged

    await userEvent.click(screen.getByLabelText("I have saved these"));
    await click("Continue");
    await waitFor(() => expect(location()).toBe("/"));
    expect(screen.queryByText(CODES[0]!)).not.toBeInTheDocument();
  });

  it("shows the server's message for a wrong code", async () => {
    setup(apiError(401, "invalid_code", "That code is not valid."));
    await type("Authentication code", "000000");
    await click("Confirm");
    expect(await screen.findByRole("alert")).toHaveTextContent("That code is not valid.");
    expect(screen.getByLabelText("Secret key")).toHaveTextContent(SECRET);
  });
});
