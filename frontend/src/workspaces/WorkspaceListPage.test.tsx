import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Workspace } from "../api/types";
import { useSession } from "../auth/SessionProvider";
import { click, renderPage, type } from "../auth/testing";
import { apiError, mockApi, verified } from "../test/utils";
import WorkspaceListPage from "./WorkspaceListPage";

function workspace(id: number, name: string, extra: Partial<Workspace> = {}): Workspace {
  return { id, name, role: "owner", deleted_at: null, ...extra };
}

function setup(deleted: Workspace[] = []) {
  const live = [workspace(1, "Team")];
  const gone = [...deleted];
  const calls = mockApi({
    "GET /auth/session": { body: verified() },
    "GET /workspaces": () => ({ body: live }),
    "GET /workspaces?deleted=true": () => ({ body: gone }),
    "POST /workspaces": (body) => {
      const { name } = body as { name: string };
      if (!name.trim()) {
        return apiError(400, "validation", "Not valid.", { name: ["A name is required."] });
      }
      const created = workspace(live.length + 1, name.trim());
      live.push(created);
      return { status: 201, body: created };
    },
    "POST /workspaces/9/restore": () => {
      const restored = gone.pop()!;
      live.push({ ...restored, deleted_at: null });
      return { body: restored };
    },
  });
  renderPage(<WorkspaceListPage />, "/", "/");
  return calls;
}

describe("WorkspaceListPage", () => {
  it("lists workspaces and creates one by name", async () => {
    const calls = setup();
    const link = await screen.findByRole("link", { name: "Team" });
    expect(link).toHaveAttribute("href", "/workspaces/1");

    await type("New workspace", "Sales");
    await click("Create");
    expect(await screen.findByRole("link", { name: "Sales" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Sales" });
    expect(screen.getByLabelText(/New workspace/)).toHaveValue("");
  });

  it("shows the server's field error for a bad name", async () => {
    setup();
    await type("New workspace", "   ");
    await click("Create");
    expect(await screen.findByText("A name is required.")).toBeInTheDocument();
  });

  it("shows restorable deleted workspaces in a separate section", async () => {
    setup([workspace(9, "Old project", { deleted_at: "2026-10-01T00:00:00Z" })]);
    const section = await screen.findByRole("region", { name: "Deleted workspaces" });
    expect(within(section).getByText("Old project")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Old project" })).not.toBeInTheDocument();

    await click("Restore Old project");
    expect(await screen.findByRole("link", { name: "Old project" })).toBeInTheDocument();
  });

  it("forgets one user's workspaces when another signs in", async () => {
    let session = verified();
    let mine = [workspace(1, "First user's team")];
    mockApi({
      "GET /auth/session": () => ({ body: session }),
      "GET /workspaces": () => ({ body: mine }),
      "GET /workspaces?deleted=true": { body: [] },
    });
    function Switch() {
      const current = useSession();
      return <button onClick={() => void current.refresh()}>Switch user</button>;
    }
    renderPage(
      <>
        <WorkspaceListPage />
        <Switch />
      </>,
      "/",
      "/",
    );
    await screen.findByRole("link", { name: "First user's team" });
    session = { ...verified(), user: { id: 2, email: "b@example.com", is_instance_admin: false } };
    mine = [workspace(5, "Second user's team")];
    await click("Switch user");
    expect(await screen.findByRole("link", { name: "Second user's team" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "First user's team" })).not.toBeInTheDocument();
  });

  it("has no deleted section when nothing can be restored", async () => {
    setup();
    await screen.findByRole("link", { name: "Team" });
    await waitFor(() =>
      expect(screen.queryByText("Deleted workspaces")).not.toBeInTheDocument(),
    );
  });
});
