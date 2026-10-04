import { Button, Center, Code, Stack, Text, TextInput } from "@mantine/core";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { messageOf, request } from "../api/client";
import type { EnrolConfirm, EnrolStart } from "../api/types";
import { AuthCard } from "./AuthCard";
import { pathForStep } from "./guards";
import RecoveryCodes from "./RecoveryCodes";
import { useSession } from "./SessionProvider";

export default function EnrolPage() {
  const session = useSession();
  const navigate = useNavigate();
  const [device, setDevice] = useState<EnrolStart | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<EnrolConfirm | null>(null);
  const started = useRef(false);

  useEffect(() => {
    // Each start replaces the pending secret, so it must happen exactly once.
    if (started.current) return;
    started.current = true;
    request<EnrolStart>("POST", "/auth/enrol/start").then(setDevice, (failure) =>
      setError(messageOf(failure)),
    );
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // The session is deliberately not refreshed yet: it is verified now, and
      // the guard would leave this page before the codes had been shown.
      setDone(
        await request<EnrolConfirm>("POST", "/auth/enrol/confirm", {
          code: code.replace(/\s+/g, ""),
        }),
      );
    } catch (failure) {
      setError(messageOf(failure));
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  async function leave(next: string | null) {
    await session.refresh();
    navigate(pathForStep(next));
  }

  if (done) {
    return (
      <AuthCard title="Save your recovery codes">
        <RecoveryCodes codes={done.recovery_codes} onContinue={() => void leave(done.next)} />
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Set up two-factor authentication" error={error}>
      <Text>
        Every account needs an authenticator app. Scan this code with yours, or type the
        key in by hand, then enter the 6-digit code it shows.
      </Text>
      {device ? (
        <Stack>
          <Center bg="white" p="md">
            <QRCodeSVG value={device.otpauth_uri} size={192} title="Authenticator QR code" />
          </Center>
          <Text size="sm">Key</Text>
          <Code block aria-label="Secret key" style={{ userSelect: "all" }}>
            {device.secret}
          </Code>
          <form onSubmit={(event) => void submit(event)}>
            <Stack>
              <TextInput
                label="Authentication code"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                value={code}
                onChange={(event) => setCode(event.currentTarget.value)}
              />
              <Button type="submit" loading={busy}>
                Confirm
              </Button>
            </Stack>
          </form>
        </Stack>
      ) : null}
    </AuthCard>
  );
}
