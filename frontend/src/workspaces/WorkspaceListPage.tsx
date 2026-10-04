import { Anchor, Badge, Button, Group, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { fieldErrors, request } from "../api/client";
import { keys, useApiMutation, useDeletedWorkspaces, useWorkspaces } from "../api/hooks";
import type { Workspace } from "../api/types";
import { Failure } from "../layout/Failure";

const LISTS = [keys.workspaces];

export default function WorkspaceListPage() {
  const workspaces = useWorkspaces();
  const deleted = useDeletedWorkspaces();
  const [name, setName] = useState("");
  const create = useApiMutation(
    (newName: string) => request<Workspace>("POST", "/workspaces", { name: newName }),
    LISTS,
  );
  const restore = useApiMutation(
    (id: number) => request<Workspace>("POST", `/workspaces/${id}/restore`),
    LISTS,
  );
  const nameErrors = fieldErrors(create.error, "name");

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(name, { onSuccess: () => setName("") });
  }

  return (
    <Stack>
      <Title order={2}>Workspaces</Title>
      <Failure error={workspaces.error ?? restore.error} />
      {workspaces.data?.length === 0 ? (
        <Text c="dimmed">You are not in any workspace yet. Create one below.</Text>
      ) : null}
      <Stack gap="xs" component="ul" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {workspaces.data?.map((workspace) => (
          <li key={workspace.id}>
            <Group gap="sm">
              <Anchor component={Link} to={`/workspaces/${workspace.id}`}>
                {workspace.name}
              </Anchor>
              {workspace.role ? <Badge variant="light">{workspace.role}</Badge> : null}
            </Group>
          </li>
        ))}
      </Stack>

      <form onSubmit={submit}>
        <Group align="flex-end">
          <TextInput
            label="New workspace"
            placeholder="Name"
            required
            value={name}
            onChange={(event) => setName(event.currentTarget.value)}
            error={nameErrors.length > 0 ? nameErrors.join(" ") : undefined}
          />
          <Button type="submit" loading={create.isPending}>
            Create
          </Button>
        </Group>
      </form>
      {nameErrors.length === 0 ? <Failure error={create.error} /> : null}

      {deleted.data && deleted.data.length > 0 ? (
        <section aria-labelledby="deleted-heading">
          <Title order={3} id="deleted-heading">
            Deleted workspaces
          </Title>
          <Text c="dimmed" size="sm">
            A deleted workspace can be restored for 30 days.
          </Text>
          <Table>
            <Table.Tbody>
              {deleted.data.map((workspace) => (
                <Table.Tr key={workspace.id}>
                  <Table.Td>{workspace.name}</Table.Td>
                  <Table.Td>
                    <Button
                      size="xs"
                      variant="default"
                      aria-label={`Restore ${workspace.name}`}
                      onClick={() => restore.mutate(workspace.id)}
                    >
                      Restore
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </section>
      ) : null}
    </Stack>
  );
}
