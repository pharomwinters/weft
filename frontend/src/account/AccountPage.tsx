import {
  Badge,
  Button,
  Center,
  Code,
  PasswordInput,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { QRCodeSVG } from "qrcode.react";
import { useState, type FormEvent } from "react";

import { fieldErrors, request } from "../api/client";
import { keys, useAccountSessions, useApiMutation } from "../api/hooks";
import type { EnrolStart, RecoveryCodesResult } from "../api/types";
import { useNewPassword } from "../auth/PasswordFields";
import RecoveryCodes from "../auth/RecoveryCodes";
import { useSession } from "../auth/SessionProvider";
import { Failure } from "../layout/Failure";

function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [done, setDone] = useState(false);
  const change = useApiMutation(
    (input: { current_password: string; new_password: string }) =>
      request("POST", "/account/password", input),
    [keys.sessions],
  );
  const errors = fieldErrors(change.error, "password");
  const password = useNewPassword(errors, "New password");

  function submit(event: FormEvent) {
    event.preventDefault();
    setDone(false);
    if (!password.check()) return;
    change.mutate(
      { current_password: current, new_password: password.value },
      { onSuccess: () => setDone(true) },
    );
  }

  return (
    <section>
      <Title order={3}>Password</Title>
      <form onSubmit={submit}>
        <Stack maw={400}>
          <PasswordInput
            label="Current password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(event) => setCurrent(event.currentTarget.value)}
          />
          {password.fields}
          {errors.length === 0 ? <Failure error={change.error} /> : null}
          {done ? (
            <Text role="status">Password changed. Your other sessions were signed out.</Text>
          ) : null}
          <Button type="submit" loading={change.isPending}>
            Change password
          </Button>
        </Stack>
      </form>
    </section>
  );
}

function SessionsSection() {
  const sessions = useAccountSessions();
  const revoke = useApiMutation(
    (id: number) => request("DELETE", `/account/sessions/${id}`),
    [keys.sessions],
  );
  return (
    <section>
      <Title order={3}>Active sessions</Title>
      <Failure error={sessions.error ?? revoke.error} />
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Device</Table.Th>
            <Table.Th>Address</Table.Th>
            <Table.Th>Last seen</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sessions.data?.map((row) => (
            <Table.Tr key={row.id}>
              <Table.Td>{row.user_agent || "Unknown device"}</Table.Td>
              <Table.Td>{row.ip}</Table.Td>
              <Table.Td>{new Date(row.last_seen).toLocaleString()}</Table.Td>
              <Table.Td>
                {row.current ? (
                  <Badge>This session</Badge>
                ) : (
                  <Button size="xs" variant="default" onClick={() => revoke.mutate(row.id)}>
                    Sign out
                  </Button>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </section>
  );
}

function TwoFactorSection() {
  const [code, setCode] = useState("");
  const [device, setDevice] = useState<EnrolStart | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const start = useApiMutation((current: string) =>
    request<EnrolStart>("POST", "/account/2fa/reenrol/start", { code: current }),
  );
  const confirm = useApiMutation((fresh: string) =>
    request<RecoveryCodesResult>("POST", "/account/2fa/reenrol/confirm", { code: fresh }),
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    const typed = code.trim();
    setCode("");
    if (device === null) {
      start.mutate(typed, { onSuccess: setDevice });
    } else {
      confirm.mutate(typed.replace(/\s+/g, ""), {
        onSuccess: (result) => {
          setDevice(null);
          setCodes(result.recovery_codes);
        },
      });
    }
  }

  if (codes) {
    return (
      <section>
        <Title order={3}>Your new recovery codes</Title>
        <RecoveryCodes codes={codes} onContinue={() => setCodes(null)} />
      </section>
    );
  }

  return (
    <section>
      <Title order={3}>Two-factor authentication</Title>
      <form onSubmit={submit}>
        <Stack maw={400}>
          {device === null ? (
            <>
              <Text>
                Replace your authenticator and recovery codes. Your current one keeps working
                until the new one is confirmed.
              </Text>
              <TextInput
                label="Current authentication or recovery code"
                autoComplete="off"
                required
                value={code}
                onChange={(event) => setCode(event.currentTarget.value)}
              />
              <Failure error={start.error} />
              <Button type="submit" variant="default" loading={start.isPending}>
                Set up a new authenticator
              </Button>
            </>
          ) : (
            <>
              <Center bg="white" p="md">
                <QRCodeSVG
                  value={device.otpauth_uri}
                  size={192}
                  title="Authenticator QR code"
                />
              </Center>
              <Code block aria-label="Secret key" style={{ userSelect: "all" }}>
                {device.secret}
              </Code>
              <TextInput
                label="Code from the new authenticator"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                value={code}
                onChange={(event) => setCode(event.currentTarget.value)}
              />
              <Failure error={confirm.error} />
              <Button type="submit" loading={confirm.isPending}>
                Confirm new authenticator
              </Button>
            </>
          )}
        </Stack>
      </form>
    </section>
  );
}

export default function AccountPage() {
  const session = useSession();
  return (
    <Stack gap="xl">
      <div>
        <Title order={2}>Account</Title>
        <Text c="dimmed">{session.user?.email}</Text>
      </div>
      <PasswordSection />
      <SessionsSection />
      <TwoFactorSection />
    </Stack>
  );
}
