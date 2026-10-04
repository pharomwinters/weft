import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
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

  const refresh = useCallback(async () => {
    try {
      // Also sets the CSRF cookie that unsafe requests send back.
      setInfo(await request<SessionInfo>("GET", "/auth/session"));
    } catch {
      setInfo(SIGNED_OUT);
    }
  }, []);

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
