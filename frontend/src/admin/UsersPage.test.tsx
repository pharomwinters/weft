import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { click, renderPage } from "../auth/testing";
import { apiError, mockApi, verified, type Reply } from "../test/utils";
import UsersPage from "./UsersPage";

const RESET_URL = "https://grid.example.com/reset/s3cr3t-token";

function setup(overrides: Record<string, Reply | ((body: unknown) => Reply)> = {}) {
  const users = [
    {
      id: 1,
      email: "admin@example.com",
      is_instance_admin: true,
      is_active: true,
      has_2fa: true,
      created_at: "2026-10-01T00:00:00Z",
    },
    {
      id: 2,
      email: "b@example.com",
      is_instance_admin: false,
      is_active: true,
      has_2fa: true,
      created_at: "2026-10-02T00:00:00Z",
    },
  ];
  const calls = mockApi({
    "GET /auth/session": { body: verified({ admin: true }) },
    "GET /admin/users": () => ({ body: users }),
    "POST /admin/users/2/deactivate": () => {
      users[1] = { ...users[1]!, is_active: false };
      return { status: 204 };
    },
    "POST /admin/users/2/reactivate": () => {
      users[1] = { ...users[1]!, is_active: true };
      return { status: 204 };
    },
    "POST /admin/users/2/reset-2fa": () => {
      users[1] = { ...users[1]!, has_2fa: false };
      return { status: 204 };
    },
    "PUT /admin/users/2/admin": () => {
      users[1] = { ...users[1]!, is_instance_admin: true };
      return { status: 204 };
    },
    "POST /admin/users/2/reset-link": {
      status: 201,
      body: { url: RESET_URL, expires_at: "2026-10-04T00:00:00Z" },
    },
    ...overrides,
  });
  renderPage(<UsersPage />, "/admin/users", "/admin/users");
  return calls;
}

const posted = (calls: { method: string; path: string }[], path: string) =>
  calls.some((c) => c.method !== "GET" && c.path === path);

describe("UsersPage", () => {
  it("shows a generated reset link once with a copy button", async () => {
    userEvent.setup(); // installs the clipboard this test then watches
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    setup();
    await click("Create reset link for b@example.com");
    expect(await screen.findByText(RESET_URL)).toBeInTheDocument();
    expect(screen.getByText("Password reset link for b@example.com")).toBeInTheDocument();
    await click("Copy link");
    expect(writeText).toHaveBeenCalledWith(RESET_URL);
    await click("Done");
    expect(screen.queryByText(RESET_URL)).not.toBeInTheDocument();
  });

  it("asks for confirmation before deactivating or resetting 2FA", async () => {
    const calls = setup();
    await click("Deactivate b@example.com");
    expect(await screen.findByRole("dialog")).toHaveTextContent("Deactivate b@example.com?");
    expect(posted(calls, "/admin/users/2/deactivate")).toBe(false);
    await click("Deactivate user");
    expect(await screen.findByText("Deactivated")).toBeInTheDocument();
    expect(posted(calls, "/admin/users/2/deactivate")).toBe(true);

    await click("Reset 2FA for b@example.com");
    expect(await screen.findByRole("dialog")).toHaveTextContent("Reset two-factor for");
    expect(posted(calls, "/admin/users/2/reset-2fa")).toBe(false);
    await click("Reset two-factor");
    expect(await screen.findByText("No 2FA yet")).toBeInTheDocument();

    await click("Reactivate b@example.com");
    await waitFor(() => expect(screen.queryByText("Deactivated")).not.toBeInTheDocument());
  });

  it("cancelling the confirmation does nothing", async () => {
    const calls = setup();
    await click("Deactivate b@example.com");
    await click("Cancel");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(calls.every((c) => c.method === "GET")).toBe(true);
  });

  it("shows the server's last_admin message when refused", async () => {
    const refusal = apiError(
      409,
      "last_admin",
      "The instance must keep at least one active admin.",
    );
    const calls = setup({
      "PUT /admin/users/1/admin": refusal,
      "POST /admin/users/1/deactivate": refusal,
    });
    await click("Remove admin from admin@example.com");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The instance must keep at least one active admin.",
    );
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ is_instance_admin: false });
  });

  it("makes a user an admin", async () => {
    const calls = setup();
    await click("Make admin b@example.com");
    expect(await screen.findByRole("button", { name: "Remove admin from b@example.com" }))
      .toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ is_instance_admin: true });
  });
});
