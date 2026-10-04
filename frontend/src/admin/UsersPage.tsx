import { Badge, Button, Group, Stack, Table, Title } from "@mantine/core";
import { useState } from "react";

import { request } from "../api/client";
import { keys, useApiMutation, useUsers } from "../api/hooks";
import type { AdminUser, ResetLink } from "../api/types";
import { ConfirmButton } from "../layout/ConfirmButton";
import { Failure } from "../layout/Failure";
import { SecretLink } from "../layout/SecretLink";

const REFRESH = [keys.users];

export default function UsersPage() {
  const users = useUsers();
  const [link, setLink] = useState<{ email: string; url: string } | null>(null);

  const setActive = useApiMutation(
    (change: { user: AdminUser; active: boolean }) =>
      request(
        "POST",
        `/admin/users/${change.user.id}/${change.active ? "reactivate" : "deactivate"}`,
      ),
    REFRESH,
  );
  const setAdmin = useApiMutation(
    (change: { user: AdminUser; admin: boolean }) =>
      request("PUT", `/admin/users/${change.user.id}/admin`, {
        is_instance_admin: change.admin,
      }),
    REFRESH,
  );
  const resetTwoFactor = useApiMutation(
    (user: AdminUser) => request("POST", `/admin/users/${user.id}/reset-2fa`),
    REFRESH,
  );
  const resetLink = useApiMutation((user: AdminUser) =>
    request<ResetLink>("POST", `/admin/users/${user.id}/reset-link`),
  );

  return (
    <Stack>
      <Title order={2}>Users</Title>
      <Failure
        error={
          users.error ??
          setActive.error ??
          setAdmin.error ??
          resetTwoFactor.error ??
          resetLink.error
        }
      />
      {link ? (
        <SecretLink
          title={`Password reset link for ${link.email}`}
          url={link.url}
          note="Give this link to the user. It works once, expires in 24 hours, and will not be shown again. They still need their authenticator to sign in."
          onDismiss={() => setLink(null)}
        />
      ) : null}
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Email</Table.Th>
            <Table.Th>Status</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {users.data?.map((user) => (
            <Table.Tr key={user.id}>
              <Table.Td>{user.email}</Table.Td>
              <Table.Td>
                <Group gap="xs">
                  {user.is_instance_admin ? <Badge>Admin</Badge> : null}
                  {user.is_active ? null : <Badge color="gray">Deactivated</Badge>}
                  {user.has_2fa ? null : <Badge color="yellow">No 2FA yet</Badge>}
                </Group>
              </Table.Td>
              <Table.Td>
                <Group gap="xs">
                  {user.is_active ? (
                    <ConfirmButton
                      label="Deactivate"
                      aria-label={`Deactivate ${user.email}`}
                      title="Deactivate user"
                      message={`Deactivate ${user.email}? They are signed out and cannot sign in until reactivated.`}
                      confirmLabel="Deactivate user"
                      onConfirm={() => setActive.mutate({ user, active: false })}
                    />
                  ) : (
                    <Button
                      size="xs"
                      variant="default"
                      aria-label={`Reactivate ${user.email}`}
                      onClick={() => setActive.mutate({ user, active: true })}
                    >
                      Reactivate
                    </Button>
                  )}
                  <Button
                    size="xs"
                    variant="default"
                    aria-label={`${user.is_instance_admin ? "Remove admin from" : "Make admin"} ${user.email}`}
                    onClick={() => setAdmin.mutate({ user, admin: !user.is_instance_admin })}
                  >
                    {user.is_instance_admin ? "Remove admin" : "Make admin"}
                  </Button>
                  <Button
                    size="xs"
                    variant="default"
                    aria-label={`Create reset link for ${user.email}`}
                    onClick={() =>
                      resetLink.mutate(user, {
                        onSuccess: (created) =>
                          setLink({ email: user.email, url: created.url }),
                      })
                    }
                  >
                    Reset link
                  </Button>
                  <ConfirmButton
                    label="Reset 2FA"
                    aria-label={`Reset 2FA for ${user.email}`}
                    title="Reset two-factor"
                    message={`Reset two-factor for ${user.email}? Their authenticator and recovery codes stop working and they set up a new one at their next sign-in.`}
                    confirmLabel="Reset two-factor"
                    onConfirm={() => resetTwoFactor.mutate(user)}
                  />
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
