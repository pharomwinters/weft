import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Role } from "../api/types";
import { click, location, renderPage } from "../auth/testing";
import { apiError, mockApi, verified } from "../test/utils";
import WorkspaceDetailPage from "./WorkspaceDetailPage";

const MEMBERS = [
  { user_id: 1, email: "u@example.com", role: "owner" },
  { user_id: 2, email: "b@example.com", role: "viewer" },
];

function setup(role: Role | null, options: { admin?: boolean } = {}) {
  let name = "Team";
  const calls = mockApi({
    "GET /auth/session": { body: verified({ admin: options.admin }) },
    "GET /workspaces/7": () => ({ body: { id: 7, name, role, deleted_at: null } }),
    "GET /workspaces/7/members": { body: MEMBERS },
    "PATCH /workspaces/7": (body) => {
      name = (body as { name: string }).name;
      return { body: { id: 7, name, role, deleted_at: null } };
    },
    "DELETE /workspaces/7": { status: 204 },
  });
  renderPage(<WorkspaceDetailPage />, "/workspaces/:id", "/workspaces/7");
  return calls;
}

describe("WorkspaceDetailPage", () => {
  it("shows an empty bases panel with explanatory text", async () => {
    setup("viewer");
    expect(await screen.findByRole("heading", { name: "Team" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Bases" })).toBeInTheDocument();
    expect(screen.getByText(/no bases yet/)).toBeInTheDocument();
  });

  it.each(["editor", "viewer"] as const)(
    "hides rename, delete and member controls from %ss",
    async (role) => {
      setup(role);
      expect(await screen.findByText("b@example.com")).toBeInTheDocument();
      expect(screen.queryByLabelText(/Workspace name/)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Delete workspace" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/Role of/)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /invitation/i })).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/Add an existing user/)).not.toBeInTheDocument();
    },
  );

  it("shows the controls to an owner", async () => {
    setup("owner");
    expect(await screen.findByLabelText(/Workspace name/)).toHaveValue("Team");
    expect(screen.getByRole("button", { name: "Delete workspace" })).toBeInTheDocument();
    expect(await screen.findByLabelText("Role of b@example.com")).toBeInTheDocument();
  });

  it("shows the controls to an admin who is not a member", async () => {
    setup(null, { admin: true });
    expect(await screen.findByLabelText(/Workspace name/)).toBeInTheDocument();
    expect(await screen.findByLabelText("Role of b@example.com")).toBeInTheDocument();
  });

  it("renames the workspace", async () => {
    const calls = setup("owner");
    const input = await screen.findByLabelText(/Workspace name/);
    await userEvent.clear(input);
    await userEvent.type(input, "Renamed");
    await click("Rename");
    expect(await screen.findByRole("heading", { name: "Renamed" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ name: "Renamed" });
  });

  it("deletes only after confirmation, then goes to the list", async () => {
    const calls = setup("owner");
    await click("Delete workspace");
    expect(await screen.findByRole("dialog")).toHaveTextContent(/restored for 30 days/);
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await click("Delete");
    await waitFor(() => expect(location()).toBe("/"));
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/workspaces/7")).toBe(true);
  });

  it("shows the server's message when the workspace is not visible", async () => {
    mockApi({
      "GET /auth/session": { body: verified() },
      "GET /workspaces/7": apiError(404, "not_found", "Not found."),
    });
    renderPage(<WorkspaceDetailPage />, "/workspaces/:id", "/workspaces/7");
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found.");
  });
});
