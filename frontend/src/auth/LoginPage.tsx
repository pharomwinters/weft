import { Button, PasswordInput, Stack, TextInput } from "@mantine/core";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiFailure, messageOf, request } from "../api/client";
import type { NextStep } from "../api/types";
import { AuthCard } from "./AuthCard";
import { pathForStep } from "./guards";
import { useSession } from "./SessionProvider";

export const LOCKED_MESSAGE = "Too many attempts. Wait 15 minutes, then try again.";
// One message whether the email is unknown or the password wrong.
const INVALID_MESSAGE = "Incorrect email or password.";

export default function LoginPage() {
  const session = useSession();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // A fresh install has no account to sign in to: go and create the admin.
    request("GET", "/setup/status").then(
      () => navigate("/setup", { replace: true }),
      () => {},
    );
  }, [navigate]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { next } = await request<NextStep>("POST", "/auth/login", { email, password });
      await session.refresh();
      navigate(pathForStep(next));
    } catch (failure) {
      if (failure instanceof ApiFailure && failure.code === "invalid_credentials") {
        setError(INVALID_MESSAGE);
      } else if (failure instanceof ApiFailure && failure.status === 429) {
        setError(LOCKED_MESSAGE);
      } else {
        setError(messageOf(failure));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Sign in" error={error}>
      <form onSubmit={(event) => void submit(event)}>
        <Stack>
          <TextInput
            label="Email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.currentTarget.value)}
          />
          <PasswordInput
            label="Password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.currentTarget.value)}
          />
          <Button type="submit" loading={busy}>
            Sign in
          </Button>
        </Stack>
      </form>
    </AuthCard>
  );
}
