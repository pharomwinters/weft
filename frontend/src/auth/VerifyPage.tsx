import { Anchor, Button, Stack, TextInput } from "@mantine/core";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiFailure, messageOf, request } from "../api/client";
import type { SecondFactor } from "../api/types";
import { AuthCard } from "./AuthCard";
import { pathForStep } from "./guards";
import { LOCKED_MESSAGE } from "./LoginPage";
import { useSession } from "./SessionProvider";

export default function VerifyPage() {
  const session = useSession();
  const navigate = useNavigate();
  const [recovery, setRecovery] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const path = recovery ? "/auth/recovery" : "/auth/verify";
      const { next } = await request<SecondFactor>("POST", path, {
        code: code.replace(/\s+/g, ""),
      });
      await session.refresh();
      navigate(pathForStep(next));
    } catch (failure) {
      if (failure instanceof ApiFailure && failure.status === 429) {
        setError(LOCKED_MESSAGE);
      } else {
        setError(messageOf(failure));
      }
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  function switchMode() {
    setRecovery(!recovery);
    setCode("");
    setError(null);
  }

  async function startOver() {
    await request("POST", "/auth/logout").catch(() => {});
    await session.refresh();
    navigate("/login");
  }

  return (
    <AuthCard title="Two-factor verification" error={error}>
      <form onSubmit={(event) => void submit(event)}>
        <Stack>
          {recovery ? (
            <TextInput
              label="Recovery code"
              description="One of the codes you saved when you set up two-factor."
              autoComplete="off"
              required
              value={code}
              onChange={(event) => setCode(event.currentTarget.value)}
            />
          ) : (
            <TextInput
              label="Authentication code"
              description="The 6-digit code from your authenticator app."
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={code}
              onChange={(event) => setCode(event.currentTarget.value)}
            />
          )}
          <Button type="submit" loading={busy}>
            Verify
          </Button>
          <Anchor component="button" type="button" size="sm" onClick={switchMode}>
            {recovery ? "Use your authenticator app instead" : "Use a recovery code instead"}
          </Anchor>
          <Anchor component="button" type="button" size="sm" onClick={() => void startOver()}>
            Sign in as someone else
          </Anchor>
        </Stack>
      </form>
    </AuthCard>
  );
}
