import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { vi } from "vitest";

import type { SessionInfo } from "../api/types";
import { SessionProvider } from "../auth/SessionProvider";

export interface Reply {
  status?: number;
  body?: unknown;
}
type Handler = Reply | ((body: unknown) => Reply);

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

/**
 * Replace fetch with a table of replies keyed "METHOD /path" (the path is
 * relative to /api/v1, query string included). Returns the calls made.
 * An unlisted request fails the test with a clear message.
 */
export function mockApi(routes: Record<string, Handler>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      const path = url.replace(/^\/api\/v1/, "");
      const body = init.body ? JSON.parse(init.body as string) : undefined;
      calls.push({ method, path, body, headers: init.headers as Record<string, string> });
      const handler = routes[`${method} ${path}`];
      if (handler === undefined) throw new Error(`Unexpected request: ${method} ${path}`);
      const reply = typeof handler === "function" ? handler(body) : handler;
      const status = reply.status ?? 200;
      return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

export function apiError(
  status: number,
  code: string,
  message = "Refused.",
  details: Record<string, unknown> = {},
): Reply {
  return { status, body: { error: { code, message, details } } };
}

export const ANONYMOUS: SessionInfo = { state: "anonymous", next: "login", user: null };

export function partial(next: string, email = "u@example.com"): SessionInfo {
  return { state: "partial", next, user: { id: 1, email, is_instance_admin: false } };
}

export function verified(options: { admin?: boolean; email?: string } = {}): SessionInfo {
  return {
    state: "verified",
    next: null,
    user: {
      id: 1,
      email: options.email ?? "u@example.com",
      is_instance_admin: options.admin ?? false,
    },
  };
}

function Location() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

/** Render inside every provider the app uses, at the given path. */
export function renderApp(ui: ReactNode, { path = "/" }: { path?: string } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <SessionProvider>
            {ui}
            <Location />
          </SessionProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}
