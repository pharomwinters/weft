const BASE = "/api/v1";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/** A request the API refused, or one that never got a usable answer. */
export class ApiFailure extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiFailure";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type AuthRequiredHandler = (failure: ApiFailure) => void;
let authRequiredHandler: AuthRequiredHandler | null = null;

/** Called whenever the server says the session is no longer adequate. */
export function onAuthRequired(handler: AuthRequiredHandler | null): void {
  authRequiredHandler = handler;
}

function csrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function failureFrom(status: number, data: unknown): ApiFailure {
  const error = (data as { error?: Record<string, unknown> } | null)?.error;
  if (!error || typeof error.code !== "string") {
    return new ApiFailure(status, "network", "The server sent an unexpected response.");
  }
  return new ApiFailure(
    status,
    error.code,
    typeof error.message === "string" ? error.message : "The request failed.",
    (error.details as Record<string, unknown> | undefined) ?? {},
  );
}

export async function request<T = void>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (!SAFE_METHODS.has(method)) {
    const token = csrfToken();
    if (token) headers["X-CSRFToken"] = token;
  }

  let response: Response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiFailure(0, "network", "The server could not be reached.");
  }
  if (response.status === 204) return undefined as T;

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ApiFailure(
      response.status,
      "network",
      "The server sent an unexpected response.",
    );
  }
  if (!response.ok) {
    const failure = failureFrom(response.status, data);
    if (failure.status === 401 && failure.code === "auth_required") {
      authRequiredHandler?.(failure);
    }
    throw failure;
  }
  return data as T;
}

/** The messages the API attached to one field, e.g. details.password. */
export function fieldErrors(failure: unknown, field: string): string[] {
  if (!(failure instanceof ApiFailure)) return [];
  const value = failure.details[field];
  return Array.isArray(value) ? value.map(String) : [];
}

export function messageOf(failure: unknown): string {
  return failure instanceof Error ? failure.message : "Something went wrong.";
}
