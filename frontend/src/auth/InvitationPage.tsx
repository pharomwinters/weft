import { Button, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiFailure, fieldErrors, messageOf, request } from "../api/client";
import type { InvitationInfo, NextStep } from "../api/types";
import { AuthCard } from "./AuthCard";
import { pathForStep } from "./guards";
import { useNewPassword } from "./PasswordFields";
import { useSession } from "./SessionProvider";

// One message for unknown, used, expired and revoked links alike.
export const DEAD_INVITATION = "This invitation is no longer valid.";

function isDead(failure: unknown): boolean {
  return failure instanceof ApiFailure && failure.code === "invalid_token";
}

export default function InvitationPage() {
  const { token = "" } = useParams();
  const session = useSession();
  const navigate = useNavigate();
  const [info, setInfo] = useState<InvitationInfo | null>(null);
  const [dead, setDead] = useState(false);
  const [email, setEmail] = useState("");
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const passwordErrors = fieldErrors(failure, "password");
  const emailErrors =
    failure instanceof ApiFailure && failure.code === "email_taken"
      ? [failure.message]
      : fieldErrors(failure, "email");
  const password = useNewPassword(passwordErrors);
  const path = `/invitations/token/${encodeURIComponent(token)}`;

  useEffect(() => {
    request<InvitationInfo>("GET", path).then(setInfo, (caught) => {
      if (isDead(caught)) setDead(true);
      else setFailure(caught);
    });
  }, [path]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password.check()) return;
    setBusy(true);
    setFailure(null);
    try {
      const { next } = await request<NextStep>("POST", `${path}/accept`, {
        email,
        password: password.value,
      });
      await session.refresh();
      navigate(pathForStep(next));
    } catch (caught) {
      if (isDead(caught)) setDead(true);
      else setFailure(caught);
    } finally {
      setBusy(false);
    }
  }

  if (dead) {
    return (
      <AuthCard title="Invitation">
        <Text role="alert">{DEAD_INVITATION}</Text>
        <Text c="dimmed">Ask the person who invited you for a new link.</Text>
      </AuthCard>
    );
  }
  const general =
    failure && passwordErrors.length === 0 && emailErrors.length === 0
      ? messageOf(failure)
      : null;

  return (
    <AuthCard title="Join" error={general}>
      {info ? (
        <>
          <Text>
            {info.workspace_name
              ? `You have been invited to the workspace ${info.workspace_name} as ${info.role}.`
              : "You have been invited to create an account."}
          </Text>
          <form onSubmit={(event) => void submit(event)}>
            <Stack>
              <TextInput
                label="Email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.currentTarget.value)}
                error={emailErrors.length > 0 ? emailErrors.join(" ") : undefined}
              />
              {password.fields}
              <Button type="submit" loading={busy}>
                Create account
              </Button>
            </Stack>
          </form>
        </>
      ) : null}
    </AuthCard>
  );
}
