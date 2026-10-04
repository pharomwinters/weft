import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { click, renderPage, type } from "../auth/testing";
import { apiError, mockApi, verified, type Reply } from "../test/utils";
import MembersTable from "./MembersTable";

const URL_ONCE = "https://grid.example.com/invite/s3cr3t-token";

function setup(overrides: Record<string, Reply | ((body: unknown) => Reply)> = {}) {
  const members = [
    { user_id: 1, email: "u@example.com", role: "owner" },
    { user_id: 2, email: "b@example.com", role: "viewer" },
  ];
  const calls = mockApi({
    "GET /auth/session": { body: verified() },
    "GET /workspaces/7/members": () => ({ body: members }),
    "PATCH /workspaces/7/members/2": (body) => {
      members[1] = { ...members[1]!, role: (body as { role: string }).role };
      return { body: members[1] };
    },
    "DELETE /workspaces/7/members/2": () => {
      members.pop();
      return { status: 204 };
    },
    "POST /workspaces/7/members": (body) => {
      const added = { user_id: 3, ...(body as { email: string; role: string }) };
      members.push(added);
      return { status: 201, body: added };
    },
    "POST /invitations": {
      status: 201,
      body: { id: 5, url: URL_ONCE, expires_at: "2026-10-10T00:00:00Z" },
    },
    ...overrides,
  });
  renderPage(<MembersTable workspaceId="7" canManage />, "/", "/");
  return calls;
}

describe("MembersTable", () => {
  it("shows the server's last_owner message when a role change is refused", async () => {
    const refusal = apiError(409, "last_owner", "A workspace must keep at least one owner.");
    setup({ "PATCH /workspaces/7/members/1": refusal });
    await userEvent.selectOptions(
      await screen.findByLabelText("Role of u@example.com"),
      "viewer",
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A workspace must keep at least one owner.",
    );
    expect(screen.getByLabelText("Role of u@example.com")).toHaveValue("owner");
  });

  it("changes a member's role", async () => {
    const calls = setup();
    await userEvent.selectOptions(
      await screen.findByLabelText("Role of b@example.com"),
      "editor",
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Role of b@example.com")).toHaveValue("editor"),
    );
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ role: "editor" });
  });

  it("removes a member only after confirmation", async () => {
    const calls = setup();
    await click("Remove b@example.com");
    expect(await screen.findByRole("dialog")).toHaveTextContent("Remove b@example.com");
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await click("Remove member");
    await waitFor(() => expect(screen.queryByText("b@example.com")).not.toBeInTheDocument());
  });

  it("adds an existing user by email", async () => {
    const calls = setup();
    await type("Add an existing user", "c@example.com");
    await userEvent.selectOptions(screen.getByLabelText("Role for the added user"), "editor");
    await click("Add");
    expect(await screen.findByText("c@example.com")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/workspaces/7/members" && c.method === "POST")?.body)
      .toEqual({ email: "c@example.com", role: "editor" });
  });

  it("creates an invitation and shows its URL once with a copy button", async () => {
    userEvent.setup(); // installs the clipboard this test then watches
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const calls = setup();
    await userEvent.selectOptions(await screen.findByLabelText("Invite someone new"), "editor");
    await click("Create invitation link");
    expect(await screen.findByText(URL_ONCE)).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/invitations")?.body).toEqual({
      workspace_id: 7,
      role: "editor",
    });

    await click("Copy link");
    expect(writeText).toHaveBeenCalledWith(URL_ONCE);
    await click("Done");
    expect(screen.queryByText(URL_ONCE)).not.toBeInTheDocument();
  });

  it("shows no controls without canManage", async () => {
    mockApi({
      "GET /auth/session": { body: verified() },
      "GET /workspaces/7/members": {
        body: [{ user_id: 1, email: "u@example.com", role: "owner" }],
      },
    });
    renderPage(<MembersTable workspaceId="7" canManage={false} />, "/", "/");
    expect(await screen.findByText("u@example.com")).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
