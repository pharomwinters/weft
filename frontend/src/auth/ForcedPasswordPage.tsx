import { Button, Stack, Text } from "@mantine/core";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { fieldErrors, messageOf, request } from "../api/client";
import type { SecondFactor } from "../api/types";
import { AuthCard } from "./AuthCard";
import { pathForStep } from "./guards";
import { useNewPassword } from "./PasswordFields";
import { useSession } from "./SessionProvider";

export default function ForcedPasswordPage() {
  const session = useSession();
  const navigate = useNavigate();
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const errors = fieldErrors(failure, "password");
  const password = useNewPassword(errors, "New password");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password.check()) return;
    setBusy(true);
    setFailure(null);
    try {
      const { next } = await request<SecondFactor>("POST", "/auth/password/forced", {
        new_password: password.value,
      });
      await session.refresh();
      navigate(pathForStep(next));
    } catch (caught) {
      setFailure(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Choose a new password"
      error={failure && errors.length === 0 ? messageOf(failure) : null}
    >
      <Text>Your password was set for you. Choose your own before you continue.</Text>
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
