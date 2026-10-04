import { Button, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";

import { request } from "../api/client";
import { keys, useApiMutation, useInvitations } from "../api/hooks";
import type { InvitationCreated } from "../api/types";
import { ConfirmButton } from "../layout/ConfirmButton";
import { Failure } from "../layout/Failure";
import { SecretLink } from "../layout/SecretLink";

const REFRESH = [keys.invitations()];

export default function InvitationsPage() {
  const invitations = useInvitations();
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const create = useApiMutation(
    () => request<InvitationCreated>("POST", "/invitations", {}),
    REFRESH,
  );
  const revoke = useApiMutation(
    (id: number) => request("DELETE", `/invitations/${id}`),
    REFRESH,
  );

  return (
    <Stack>
      <Title order={2}>Invitations</Title>
      <Text c="dimmed">
        An invitation link lets one new person create an account. To invite someone straight
        into a workspace, use that workspace&apos;s members section.
      </Text>
      <div>
        <Button
          loading={create.isPending}
          onClick={() => create.mutate(undefined, { onSuccess: setCreated })}
        >
          Create invitation link
        </Button>
      </div>
      <Failure error={invitations.error ?? create.error ?? revoke.error} />
      {created ? (
        <SecretLink
          title="Invitation link"
          url={created.url}
          note="Send this link to the person you are inviting. It works once, expires in 7 days, and will not be shown again."
          onDismiss={() => setCreated(null)}
        />
      ) : null}
      {invitations.data?.length === 0 ? <Text>No pending invitations.</Text> : null}
      {invitations.data && invitations.data.length > 0 ? (
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>For</Table.Th>
              <Table.Th>Created by</Table.Th>
              <Table.Th>Expires</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {invitations.data.map((invitation) => (
              <Table.Tr key={invitation.id}>
                <Table.Td>
                  {invitation.workspace_name
                    ? `${invitation.workspace_name} (${invitation.role})`
                    : "An account"}
                </Table.Td>
                <Table.Td>{invitation.created_by_email}</Table.Td>
                <Table.Td>{new Date(invitation.expires_at).toLocaleString()}</Table.Td>
                <Table.Td>
                  <ConfirmButton
                    label="Revoke"
                    title="Revoke invitation"
                    message="Revoke this invitation? Its link stops working."
                    confirmLabel="Revoke invitation"
                    onConfirm={() => revoke.mutate(invitation.id)}
                  />
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      ) : null}
    </Stack>
  );
}
