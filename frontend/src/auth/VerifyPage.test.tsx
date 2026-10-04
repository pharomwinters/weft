import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SessionInfo } from "../api/types";
import { apiError, mockApi, partial, verified, type Reply } from "../test/utils";
import { click, location, renderPage, type } from "./testing";
import VerifyPage from "./VerifyPage";

function setup(replies: { verify?: Reply; recovery?: Reply }) {
  let session: SessionInfo = partial("verify");
  const succeed = (reply: Reply | undefined) => () => {
    const answer = reply ?? { body: { next: null } };
    if ((answer.status ?? 200) === 200) session = verified();
    return answer;
  };
  const calls = mockApi({
    "GET /auth/session": () => ({ body: session }),
    "POST /auth/verify": succeed(replies.verify),
    "POST /auth/recovery": succeed(replies.recovery),
  });
  renderPage(<VerifyPage />, "/verify", "/verify");
  return calls;
}

describe("VerifyPage", () => {
  it("strips spaces from the code before sending", async () => {
    const calls = setup({});
    await type("Authentication code", " 012 345 ");
    await click("Verify");
    await waitFor(() => expect(location()).toBe("/"));
    expect(calls.find((c) => c.path === "/auth/verify")?.body).toEqual({ code: "012345" });
  });

  it("has a switch to recovery-code entry that posts to /auth/recovery", async () => {
    const calls = setup({});
    await click("Use a recovery code instead");
    await type("Recovery code", "abcd-efgh-ijkl-mnop");
    await click("Verify");
    await waitFor(() => expect(location()).toBe("/"));
    expect(calls.find((c) => c.path === "/auth/recovery")?.body).toEqual({
      code: "abcd-efgh-ijkl-mnop",
    });
    expect(calls.some((c) => c.path === "/auth/verify")).toBe(false);
  });

  it("shows the server's message for a wrong code and clears the field", async () => {
    setup({ verify: apiError(401, "invalid_code", "That code is not valid.") });
    await type("Authentication code", "000000");
    await click("Verify");
    expect(await screen.findByRole("alert")).toHaveTextContent("That code is not valid.");
    expect(screen.getByLabelText(/Authentication code/)).toHaveValue("");
    expect(location()).toBe("/verify");
  });

  it("goes on to the password change when the server names it", async () => {
    setup({ verify: { status: 200, body: { next: "change_password" } } });
    await type("Authentication code", "123456");
    await click("Verify");
    await waitFor(() => expect(location()).toBe("/change-password"));
  });
});
