import { useQuery } from "@tanstack/react-query";

import { request } from "./client";
import type { Workspace } from "./types";

export const keys = {
  workspaces: ["workspaces"] as const,
};

export function useWorkspaces() {
  return useQuery({
    queryKey: keys.workspaces,
    queryFn: () => request<Workspace[]>("GET", "/workspaces"),
  });
}
