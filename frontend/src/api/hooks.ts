import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";

import { request } from "./client";
import type {
  AccountSession,
  AdminUser,
  AuditPage,
  Invitation,
  Member,
  Workspace,
} from "./types";

export const keys = {
  workspaces: ["workspaces"] as const,
  deletedWorkspaces: ["workspaces", "deleted"] as const,
  workspace: (id: string) => ["workspaces", id] as const,
  members: (id: string) => ["workspaces", id, "members"] as const,
  invitations: (workspaceId?: string) => ["invitations", workspaceId ?? "all"] as const,
  sessions: ["account", "sessions"] as const,
  users: ["admin", "users"] as const,
  audit: (event: string) => ["admin", "audit", event] as const,
};

export function useWorkspaces() {
  return useQuery({
    queryKey: keys.workspaces,
    queryFn: () => request<Workspace[]>("GET", "/workspaces"),
  });
}

export function useDeletedWorkspaces() {
  return useQuery({
    queryKey: keys.deletedWorkspaces,
    queryFn: () => request<Workspace[]>("GET", "/workspaces?deleted=true"),
  });
}

export function useWorkspace(id: string) {
  return useQuery({
    queryKey: keys.workspace(id),
    queryFn: () => request<Workspace>("GET", `/workspaces/${id}`),
  });
}

export function useMembers(id: string) {
  return useQuery({
    queryKey: keys.members(id),
    queryFn: () => request<Member[]>("GET", `/workspaces/${id}/members`),
  });
}

export function useInvitations(workspaceId?: string, enabled = true) {
  const query = workspaceId ? `?workspace_id=${workspaceId}` : "";
  return useQuery({
    queryKey: keys.invitations(workspaceId),
    queryFn: () => request<Invitation[]>("GET", `/invitations${query}`),
    enabled,
  });
}

export function useAccountSessions() {
  return useQuery({
    queryKey: keys.sessions,
    queryFn: () => request<AccountSession[]>("GET", "/account/sessions"),
  });
}

export function useUsers() {
  return useQuery({
    queryKey: keys.users,
    queryFn: () => request<AdminUser[]>("GET", "/admin/users"),
  });
}

/** Audit events, newest first; fetchNextPage follows the server's next_before. */
export function useAuditLog(event: string) {
  return useInfiniteQuery({
    queryKey: keys.audit(event),
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams();
      if (event) params.set("event", event);
      if (pageParam !== null) params.set("before", String(pageParam));
      const query = params.toString();
      return request<AuditPage>("GET", `/admin/audit${query ? `?${query}` : ""}`);
    },
    getNextPageParam: (last) => last.next_before,
  });
}

/** A mutation that refetches the given queries once it succeeds. */
export function useApiMutation<TInput, TResult = void>(
  run: (input: TInput) => Promise<TResult>,
  invalidate: QueryKey[] = [],
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: async () => {
      await Promise.all(
        invalidate.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
      );
    },
  });
}
