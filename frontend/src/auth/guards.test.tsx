import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { request } from "../api/client";
import type { SessionInfo } from "../api/types";
import AppRoutes from "../routes";
import { ANONYMOUS, apiError, mockApi, partial, renderApp, verified } from "../test/utils";
import { pathForStep, RequireAdmin, RequirePartial, RequireVerified } from "./guards";

function location(): string | null {
  return screen.getByTestId("location").textContent;
}

function guarded(session: SessionInfo, path = "/") {
  mockApi({ "GET /auth/session": { body: session } });
  renderApp(
    <Routes>
      <Route
        path="/"
        element={
          <RequireVerified>
            <p>Private page</p>
          </RequireVerified>
        }
      />
      <Route
        path="/admin"
        element={
          <RequireVerified>
            <RequireAdmin>
              <p>Admin page</p>
            </RequireAdmin>
          </RequireVerified>
        }
      />
      <Route
        path="/verify"
        element={
          <RequirePartial step="verify">
            <p>Code entry</p>
          </RequirePartial>
        }
      />
      <Route path="*" element={<p>Elsewhere</p>} />
    </Routes>,
    { path },
  );
}

describe("pathForStep", () => {
  it.each([
    ["login", "/login"],
    ["verify", "/verify"],
    ["enrol", "/enrol"],
    ["change_password", "/change-password"],
  ])("pathForStep(%s) is %s", (step, path) => {
    expect(pathForStep(step)).toBe(path);
  });

  it("sends a finished login home and an unknown step to /login", () => {
    expect(pathForStep(null)).toBe("/");
    expect(pathForStep("something-new")).toBe("/login");
  });
});

describe("guards", () => {
  it("RequireVerified shows the page to a verified session", async () => {
    guarded(verified());
    expect(await screen.findByText("Private page")).toBeInTheDocument();
  });

  it("RequireVerified redirects an anonymous session to /login", async () => {
    guarded(ANONYMOUS);
    await waitFor(() => expect(location()).toBe("/login"));
    expect(screen.queryByText("Private page")).not.toBeInTheDocument();
  });

  it("RequireVerified redirects a partial session to the step the server named", async () => {
    guarded(partial("enrol"));
    await waitFor(() => expect(location()).toBe("/enrol"));
    expect(screen.queryByText("Private page")).not.toBeInTheDocument();
  });

  it("RequirePartial shows only the step that is due", async () => {
    guarded(partial("verify"), "/verify");
    expect(await screen.findByText("Code entry")).toBeInTheDocument();
  });

  it("RequirePartial sends a session at another step to that step", async () => {
    guarded(partial("change_password"), "/verify");
    await waitFor(() => expect(location()).toBe("/change-password"));
  });

  it("RequirePartial sends a verified session home", async () => {
    guarded(verified(), "/verify");
    await waitFor(() => expect(location()).toBe("/"));
  });

  it("RequireAdmin shows a not-permitted message to a non-admin", async () => {
    guarded(verified(), "/admin");
    expect(await screen.findByText("Not permitted")).toBeInTheDocument();
    expect(screen.queryByText("Admin page")).not.toBeInTheDocument();
  });

  it("RequireAdmin shows the page to an admin", async () => {
    guarded(verified({ admin: true }), "/admin");
    expect(await screen.findByText("Admin page")).toBeInTheDocument();
  });

  it("a 401 from any request refreshes the session and redirects by details.next", async () => {
    let session: SessionInfo = verified();
    mockApi({
      "GET /auth/session": () => ({ body: session }),
      "GET /workspaces": () =>
        apiError(401, "auth_required", "Sign in.", { session: "partial", next: "verify" }),
    });
    renderApp(
      <Routes>
        <Route
          path="/"
          element={
            <RequireVerified>
              <button onClick={() => void request("GET", "/workspaces").catch(() => {})}>
                Load
              </button>
            </RequireVerified>
          }
        />
        <Route path="*" element={<p>Elsewhere</p>} />
      </Routes>,
    );
    const button = await screen.findByRole("button", { name: "Load" });
    session = partial("verify"); // the server-side session lapsed
    await userEvent.click(button);
    await waitFor(() => expect(location()).toBe("/verify"));
  });
});

describe("shell", () => {
  it("shows admin links only to admins, and the signed-in email", async () => {
    mockApi({ "GET /auth/session": { body: verified({ email: "me@example.com" }) } });
    const { unmount } = renderApp(<AppRoutes />);
    expect(await screen.findByText("me@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Workspaces" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
    unmount();

    mockApi({ "GET /auth/session": { body: verified({ admin: true }) } });
    renderApp(<AppRoutes />);
    expect(await screen.findByRole("link", { name: "Audit log" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Users" })).toBeInTheDocument();
  });

  it("signs out and goes to /login", async () => {
    let session: SessionInfo = verified();
    const calls = mockApi({
      "GET /auth/session": () => ({ body: session }),
      "POST /auth/logout": () => {
        session = ANONYMOUS;
        return { status: 204 };
      },
    });
    renderApp(<AppRoutes />);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(location()).toBe("/login"));
    expect(calls.some((c) => c.method === "POST" && c.path === "/auth/logout")).toBe(true);
  });
});
