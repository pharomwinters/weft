import { Alert, Center, Loader } from "@mantine/core";
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useSession } from "./SessionProvider";

const STEP_PATHS: Record<string, string> = {
  login: "/login",
  verify: "/verify",
  enrol: "/enrol",
  change_password: "/change-password",
};

/** Where the step the server named lives; null (nothing left to do) is home. */
export function pathForStep(next: string | null): string {
  return next === null ? "/" : (STEP_PATHS[next] ?? "/login");
}

function Waiting() {
  return (
    <Center h="60vh">
      <Loader aria-label="Loading" />
    </Center>
  );
}

// These guards mirror the server's session states for convenience only: the
// server refuses whatever a guard would have hidden.

export function RequireVerified({ children }: { children: ReactNode }) {
  const session = useSession();
  if (session.state === "loading") return <Waiting />;
  if (session.state !== "verified") {
    return <Navigate to={pathForStep(session.next ?? "login")} replace />;
  }
  return <>{children}</>;
}

/** For the screens of a half-finished login: only the step that is due. */
export function RequirePartial({ step, children }: { step: string; children: ReactNode }) {
  const session = useSession();
  if (session.state === "loading") return <Waiting />;
  if (session.state !== "partial" || session.next !== step) {
    return <Navigate to={pathForStep(session.next)} replace />;
  }
  return <>{children}</>;
}

/** For screens that only make sense signed out (login, setup, invitation). */
export function RequireAnonymous({ children }: { children: ReactNode }) {
  const session = useSession();
  if (session.state === "loading") return <Waiting />;
  if (session.state !== "anonymous") {
    return <Navigate to={pathForStep(session.next)} replace />;
  }
  return <>{children}</>;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const session = useSession();
  if (!session.user?.is_instance_admin) {
    return (
      <Alert color="red" title="Not permitted">
        Only an instance admin can open this page.
      </Alert>
    );
  }
  return <>{children}</>;
}
