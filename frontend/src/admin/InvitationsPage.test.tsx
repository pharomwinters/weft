import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { click, renderPage } from "../auth/testing";
import { mockApi, verified } from "../test/utils";
import InvitationsPage from "./InvitationsPage";

const URL_ONCE = "https://grid.example.com/invite/s3cr3t-token";

function setup() {
  const pending = [
    {
      id: 4,
      workspace_id: 7,
      workspace_name: "Team",
      role: "viewer",
      created_by_email: "owner@example.com",
      expires_at: "2026-10-10T00:00:00Z",
    },
  ];
  const calls = mockApi({
    "GET /auth/session": { body: verified({ admin: true }) },
    "GET /invitations": () => ({ body: pending }),
    "POST /invitations": () => {
      pending.push({ ...pending[0]!, id: 5, workspace_id: 0, workspace_name: "", role: "" });
      return { status: 201, body: { id: 5, url: URL_ONCE, expires_at: "2026-10-10T00:00:00Z" } };
    },
    "DELETE /invitations/4": () => {
      pending.shift();
      return { status: 204 };
    },
  });
  renderPage(<InvitationsPage />, "/admin/invitations", "/admin/invitations");
  return calls;
}

describe("InvitationsPage", () => {
  it("lists pending invitations without their links", async () => {
    setup();
    expect(await screen.findByText("Team (viewer)")).toBeInTheDocument();
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.queryByText(/\/invite\//)).not.toBeInTheDocument();
  });

  it("creates an instance invitation and shows its URL once", async () => {
    const calls = setup();
    await click("Create invitation link");
    expect(await screen.findByText(URL_ONCE)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({});
    expect(await screen.findByText("An account")).toBeInTheDocument();
    await click("Done");
    expect(screen.queryByText(URL_ONCE)).not.toBeInTheDocument();
  });

  it("revokes an invitation after confirmation", async () => {
    const calls = setup();
    await click("Revoke");
    expect(await screen.findByRole("dialog")).toHaveTextContent("Its link stops working.");
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await click("Revoke invitation");
    await waitFor(() => expect(screen.queryByText("Team (viewer)")).not.toBeInTheDocument());
    expect(await screen.findByText("No pending invitations.")).toBeInTheDocument();
  });
});
