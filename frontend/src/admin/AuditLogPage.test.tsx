import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { click, renderPage } from "../auth/testing";
import { mockApi, verified } from "../test/utils";
import AuditLogPage, { AUDIT_EVENTS } from "./AuditLogPage";

function row(id: number, event: string, details: Record<string, unknown> = {}) {
  return {
    id,
    time: "2026-10-03T10:00:00Z",
    event,
    actor_email: "admin@example.com",
    target_type: "user",
    target_id: String(id),
    ip: "203.0.113.9",
    details,
  };
}

function setup() {
  const calls = mockApi({
    "GET /auth/session": { body: verified({ admin: true }) },
    "GET /admin/audit": {
      body: { items: [row(30, "logout"), row(29, "login_success")], next_before: 29 },
    },
    "GET /admin/audit?before=29": {
      body: { items: [row(28, "workspace_created", { name: "Team" })], next_before: null },
    },
    "GET /admin/audit?event=lockout": {
      body: { items: [row(12, "lockout", { scope: "ip" })], next_before: 12 },
    },
    "GET /admin/audit?event=lockout&before=12": {
      body: { items: [row(3, "lockout", { scope: "account" })], next_before: null },
    },
  });
  renderPage(<AuditLogPage />, "/admin/audit", "/admin/audit");
  return calls;
}

describe("AuditLogPage", () => {
  it("filters by event type and loads older entries with next_before", async () => {
    const calls = setup();
    expect(await screen.findByRole("cell", { name: "logout" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "login_success" })).toBeInTheDocument();

    await click("Load older entries");
    expect(await screen.findByRole("cell", { name: "workspace_created" })).toBeInTheDocument();
    expect(screen.getByText('{"name":"Team"}')).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "logout" })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Load older entries" })).not.toBeInTheDocument(),
    );

    await userEvent.selectOptions(screen.getByLabelText("Event type"), "lockout");
    expect(await screen.findByText('{"scope":"ip"}')).toBeInTheDocument();
    expect(screen.queryByRole("cell", { name: "logout" })).not.toBeInTheDocument();

    await click("Load older entries");
    expect(await screen.findByText('{"scope":"account"}')).toBeInTheDocument();
    expect(calls.map((c) => c.path).filter((p) => p.startsWith("/admin/audit"))).toEqual([
      "/admin/audit",
      "/admin/audit?before=29",
      "/admin/audit?event=lockout",
      "/admin/audit?event=lockout&before=12",
    ]);
  });

  it("offers every event type the server records", () => {
    expect(AUDIT_EVENTS).toHaveLength(22);
    expect(new Set(AUDIT_EVENTS).size).toBe(22);
  });
});
