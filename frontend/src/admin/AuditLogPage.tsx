import { Button, Code, NativeSelect, Stack, Table, Title } from "@mantine/core";
import { useState } from "react";

import { useAuditLog } from "../api/hooks";
import { Failure } from "../layout/Failure";

// The event names the server records (backend/audit/events.py).
export const AUDIT_EVENTS = [
  "login_success",
  "login_failure",
  "lockout",
  "logout",
  "totp_enrolled",
  "recovery_code_used",
  "password_changed",
  "reset_link_created",
  "reset_link_used",
  "twofa_reset",
  "invitation_created",
  "invitation_accepted",
  "user_deactivated",
  "user_reactivated",
  "admin_flag_changed",
  "membership_added",
  "membership_changed",
  "membership_removed",
  "workspace_created",
  "workspace_deleted",
  "workspace_restored",
  "setup_completed",
];

export default function AuditLogPage() {
  const [event, setEvent] = useState("");
  const log = useAuditLog(event);
  const rows = log.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <Stack>
      <Title order={2}>Audit log</Title>
      <NativeSelect
        label="Event type"
        maw={300}
        data={[{ value: "", label: "All events" }, ...AUDIT_EVENTS]}
        value={event}
        onChange={(change) => setEvent(change.currentTarget.value)}
      />
      <Failure error={log.error} />
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Time</Table.Th>
            <Table.Th>Event</Table.Th>
            <Table.Th>Actor</Table.Th>
            <Table.Th>Target</Table.Th>
            <Table.Th>Address</Table.Th>
            <Table.Th>Details</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => (
            <Table.Tr key={row.id}>
              <Table.Td>{new Date(row.time).toLocaleString()}</Table.Td>
              <Table.Td>{row.event}</Table.Td>
              <Table.Td>{row.actor_email}</Table.Td>
              <Table.Td>{row.target_type ? `${row.target_type} ${row.target_id}` : ""}</Table.Td>
              <Table.Td>{row.ip}</Table.Td>
              <Table.Td>
                {Object.keys(row.details).length > 0 ? (
                  <Code>{JSON.stringify(row.details)}</Code>
                ) : null}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {log.hasNextPage ? (
        <div>
          <Button
            variant="default"
            loading={log.isFetchingNextPage}
            onClick={() => void log.fetchNextPage()}
          >
            Load older entries
          </Button>
        </div>
      ) : null}
    </Stack>
  );
}
