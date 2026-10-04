import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { onAuthRequired, request } from "../api/client";
import type { SessionInfo, User } from "../api/types";

export type SessionState = "loading" | "anonymous" | "partial" | "verified";

export interface Session {
  state: SessionState;
  /** The step the server wants next; null once verified. */
  next: string | null;
  user: User | null;
  refresh(): Promise<void>;
}

const SessionContext = createContext<Session | null>(null);

const SIGNED_OUT = { state: "anonymous", next: "login", user: null } as const;

export function SessionProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<Omit<Session, "refresh">>({
    state: "loading",
    next: null,
    user: null,
  });

  const queryClient = useQueryClient();
  // Whose data the query cache holds; undefined until the first check.
  const cachedFor = useRef<number | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    let fresh: SessionInfo;
    try {
      // Also sets the CSRF cookie that unsafe requests send back.
      fresh = await request<SessionInfo>("GET", "/auth/session");
    } catch {
      // A failed check is not a sign-out: keep what we knew, unless this was
      // the first check and there is nothing to keep.
      setInfo((known) => (known.state === "loading" ? SIGNED_OUT : known));
      return;
    }
    // Cached server data belongs to whoever was verified when it was fetched.
    const owner = fresh.state === "verified" ? (fresh.user?.id ?? null) : null;
    if (cachedFor.current !== undefined && owner !== cachedFor.current) {
      // Drop what is not on screen; whatever still is starts again from
      // nothing once someone is signed in.
      queryClient.removeQueries({ type: "inactive" });
      if (owner !== null) void queryClient.resetQueries();
    }
    cachedFor.current = owner;
    setInfo(fresh);
  }, [queryClient]);

  useEffect(() => {
    void refresh();
    // Any request the server refuses for lack of a session re-reads the
    // session; the guards then route to the step it names.
    onAuthRequired(() => void refresh());
    return () => onAuthRequired(null);
  }, [refresh]);

  const session = useMemo(() => ({ ...info, refresh }), [info, refresh]);
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) throw new Error("useSession needs a SessionProvider above it");
  return session;
}
