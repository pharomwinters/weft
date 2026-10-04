import { Button, Group, Paper, Stack, Text, TextInput, Title } from "@mantine/core";
import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fieldErrors, request } from "../api/client";
import { keys, useApiMutation, useWorkspace } from "../api/hooks";
import type { Workspace } from "../api/types";
import { useSession } from "../auth/SessionProvider";
import { ConfirmButton } from "../layout/ConfirmButton";
import { Failure } from "../layout/Failure";
import MembersTable from "./MembersTable";

export default function WorkspaceDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const session = useSession();
  const workspace = useWorkspace(id);
  const [name, setName] = useState<string | null>(null);

  const rename = useApiMutation(
    (newName: string) => request<Workspace>("PATCH", `/workspaces/${id}`, { name: newName }),
    [keys.workspaces],
  );
  const remove = useApiMutation(() => request("DELETE", `/workspaces/${id}`), [keys.workspaces]);

  if (workspace.error) return <Failure error={workspace.error} />;
  if (!workspace.data) return null;

  // Mirrors the server's role table; the server remains the authority.
  const canManage =
    workspace.data.role === "owner" || Boolean(session.user?.is_instance_admin);
  const nameErrors = fieldErrors(rename.error, "name");

  function submitRename(event: FormEvent) {
    event.preventDefault();
    if (name !== null) rename.mutate(name, { onSuccess: () => setName(null) });
  }

  return (
    <Stack>
      <Title order={2}>{workspace.data.name}</Title>

      <Paper withBorder p="md">
        <Title order={3}>Bases</Title>
        <Text c="dimmed">
          This workspace has no bases yet. Bases, the tables and grids that hold your data,
          arrive in a later release.
        </Text>
      </Paper>

      <MembersTable workspaceId={id} canManage={canManage} />

      {canManage ? (
        <Stack>
          <Title order={3}>Settings</Title>
          <form onSubmit={submitRename}>
            <Group align="flex-end">
              <TextInput
                label="Workspace name"
                required
                value={name ?? workspace.data.name}
                onChange={(event) => setName(event.currentTarget.value)}
                error={nameErrors.length > 0 ? nameErrors.join(" ") : undefined}
              />
              <Button type="submit" variant="default" loading={rename.isPending}>
                Rename
              </Button>
            </Group>
          </form>
          <Failure error={(nameErrors.length === 0 ? rename.error : null) ?? remove.error} />
          <div>
            <ConfirmButton
              label="Delete workspace"
              color="red"
              variant="outline"
              title="Delete workspace"
              message={`Delete ${workspace.data.name}? It can be restored for 30 days.`}
              confirmLabel="Delete"
              onConfirm={() => remove.mutate(undefined, { onSuccess: () => navigate("/") })}
            />
          </div>
        </Stack>
      ) : null}
    </Stack>
  );
}
