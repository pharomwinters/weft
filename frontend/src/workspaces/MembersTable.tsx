import { Button, Group, NativeSelect, Stack, Table, TextInput, Title } from "@mantine/core";
import { useState, type FormEvent } from "react";

import { request } from "../api/client";
import { keys, useApiMutation, useMembers } from "../api/hooks";
import type { InvitationCreated, Member, Role } from "../api/types";
import { ConfirmButton } from "../layout/ConfirmButton";
import { Failure } from "../layout/Failure";
import { SecretLink } from "../layout/SecretLink";

const ROLES: Role[] = ["owner", "editor", "viewer"];

/**
 * A workspace's members. With `canManage`, also the controls to change roles,
 * remove, add and invite. Hiding them is a convenience: the server decides.
 */
export default function MembersTable({
  workspaceId,
  canManage,
}: {
  workspaceId: string;
  canManage: boolean;
}) {
  const base = `/workspaces/${workspaceId}/members`;
  const refresh = [keys.members(workspaceId)];
  const members = useMembers(workspaceId);
  const [email, setEmail] = useState("");
  const [addRole, setAddRole] = useState<Role>("viewer");
  const [inviteRole, setInviteRole] = useState<Role>("viewer");
  const [invitation, setInvitation] = useState<InvitationCreated | null>(null);

  const changeRole = useApiMutation(
    (change: { userId: number; role: Role }) =>
      request<Member>("PATCH", `${base}/${change.userId}`, { role: change.role }),
    refresh,
  );
  const remove = useApiMutation(
    (userId: number) => request("DELETE", `${base}/${userId}`),
    refresh,
  );
  const add = useApiMutation(
    (input: { email: string; role: Role }) => request<Member>("POST", base, input),
    refresh,
  );
  const invite = useApiMutation((role: Role) =>
    request<InvitationCreated>("POST", "/invitations", {
      workspace_id: Number(workspaceId),
      role,
    }),
  );

  function submitAdd(event: FormEvent) {
    event.preventDefault();
    add.mutate({ email, role: addRole }, { onSuccess: () => setEmail("") });
  }

  return (
    <Stack>
      <Title order={3}>Members</Title>
      <Failure error={members.error ?? changeRole.error ?? remove.error} />
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Email</Table.Th>
            <Table.Th>Role</Table.Th>
            {canManage ? <Table.Th /> : null}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {members.data?.map((member) => (
            <Table.Tr key={member.user_id}>
              <Table.Td>{member.email}</Table.Td>
              <Table.Td>
                {canManage ? (
                  <NativeSelect
                    aria-label={`Role of ${member.email}`}
                    data={ROLES}
                    value={member.role}
                    onChange={(event) =>
                      changeRole.mutate({
                        userId: member.user_id,
                        role: event.currentTarget.value as Role,
                      })
                    }
                  />
                ) : (
                  member.role
                )}
              </Table.Td>
              {canManage ? (
                <Table.Td>
                  <ConfirmButton
                    label="Remove"
                    aria-label={`Remove ${member.email}`}
                    title="Remove member"
                    message={`Remove ${member.email} from this workspace?`}
                    confirmLabel="Remove member"
                    onConfirm={() => remove.mutate(member.user_id)}
                  />
                </Table.Td>
              ) : null}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      {canManage ? (
        <>
          <form onSubmit={submitAdd}>
            <Group align="flex-end">
              <TextInput
                label="Add an existing user"
                type="email"
                placeholder="Email"
                required
                value={email}
                onChange={(event) => setEmail(event.currentTarget.value)}
              />
              <NativeSelect
                aria-label="Role for the added user"
                data={ROLES}
                value={addRole}
                onChange={(event) => setAddRole(event.currentTarget.value as Role)}
              />
              <Button type="submit" loading={add.isPending}>
                Add
              </Button>
            </Group>
          </form>
          <Failure error={add.error} />

          <Group align="flex-end">
            <NativeSelect
              label="Invite someone new"
              data={ROLES}
              value={inviteRole}
              onChange={(event) => setInviteRole(event.currentTarget.value as Role)}
            />
            <Button
              variant="default"
              loading={invite.isPending}
              onClick={() => invite.mutate(inviteRole, { onSuccess: setInvitation })}
            >
              Create invitation link
            </Button>
          </Group>
          <Failure error={invite.error} />
          {invitation ? (
            <SecretLink
              title="Invitation link"
              url={invitation.url}
              note="Send this link to the person you are inviting. It works once, expires in 7 days, and will not be shown again."
              onDismiss={() => setInvitation(null)}
            />
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}
