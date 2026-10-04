import { Anchor, Button, Stack, Text } from "@mantine/core";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiFailure, fieldErrors, messageOf, request } from "../api/client";
import { AuthCard } from "./AuthCard";
import { useNewPassword } from "./PasswordFields";

export const DEAD_RESET_LINK = "This reset link is no longer valid.";

function isDead(failure: unknown): boolean {
  return failure instanceof ApiFailure && failure.code === "invalid_token";
}

export default function ResetPage() {
  const { token = "" } = useParams();
  const [stage, setStage] = useState<"checking" | "open" | "dead" | "done">("checking");
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const errors = fieldErrors(failure, "password");
  const password = useNewPassword(errors, "New password");
  const path = `/auth/reset/${encodeURIComponent(token)}`;

  useEffect(() => {
    request("GET", path).then(
      () => setStage("open"),
      (caught) => {
        if (isDead(caught)) setStage("dead");
        else {
          setFailure(caught);
          setStage("open");
        }
      },
    );
  }, [path]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password.check()) return;
    setBusy(true);
    setFailure(null);
    try {
      await request("POST", path, { new_password: password.value });
      setStage("done");
    } catch (caught) {
      if (isDead(caught)) setStage("dead");
      else setFailure(caught);
    } finally {
      setBusy(false);
    }
  }

  if (stage === "checking") return null;
  if (stage === "dead") {
    return (
      <AuthCard title="Reset password">
        <Text role="alert">{DEAD_RESET_LINK}</Text>
        <Text c="dimmed">Ask an admin for a new link.</Text>
      </AuthCard>
    );
  }
  if (stage === "done") {
    return (
      <AuthCard title="Password changed">
        <Text>
          Your password has been changed. You still need your authenticator code to sign in.
        </Text>
        <Anchor component={Link} to="/login">
          Sign in
        </Anchor>
      </AuthCard>
    );
  }
  return (
    <AuthCard
      title="Choose a new password"
      error={failure && errors.length === 0 ? messageOf(failure) : null}
    >
      <form onSubmit={(event) => void submit(event)}>
        <Stack>
          {password.fields}
          <Button type="submit" loading={busy}>
            Change password
          </Button>
        </Stack>
      </form>
    </AuthCard>
  );
}
