import { Button, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiFailure, fieldErrors, messageOf, request } from "../api/client";
import type { NextStep } from "../api/types";
import { AuthCard } from "./AuthCard";
import { pathForStep } from "./guards";
import { useNewPassword } from "./PasswordFields";
import { useSession } from "./SessionProvider";

export default function SetupPage() {
  const session = useSession();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const passwordErrors = fieldErrors(failure, "password");
  const emailErrors = fieldErrors(failure, "email");
  const password = useNewPassword(passwordErrors);

  useEffect(() => {
    // Once an admin exists the server answers 404 and setup is closed for good.
    request("GET", "/setup/status").then(
      () => setOpen(true),
      () => navigate("/login", { replace: true }),
    );
  }, [navigate]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password.check()) return;
    setBusy(true);
    setFailure(null);
    try {
      const { next } = await request<NextStep>("POST", "/setup/admin", {
        token: token.trim(),
        email,
        password: password.value,
      });
      await session.refresh();
      navigate(pathForStep(next));
    } catch (caught) {
      if (caught instanceof ApiFailure && caught.status === 404) {
        navigate("/login", { replace: true });
        return;
      }
      setFailure(caught);
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;
  const general =
    failure && passwordErrors.length === 0 && emailErrors.length === 0
      ? messageOf(failure)
      : null;

  return (
    <AuthCard title="Create the admin account" error={general}>
      <Text>
        This instance has no admin yet. The server printed a setup token to its log when it
        started; paste it here to prove you run this server.
      </Text>
      <form onSubmit={(event) => void submit(event)}>
        <Stack>
          <TextInput
            label="Setup token"
            autoComplete="off"
            required
            value={token}
            onChange={(event) => setToken(event.currentTarget.value)}
          />
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
            Create admin
          </Button>
        </Stack>
      </form>
    </AuthCard>
  );
}
