import { Alert, Center, Paper, Stack, Title } from "@mantine/core";
import type { ReactNode } from "react";

import { APP_NAME } from "../constants";

/** The frame every signed-out screen shares. */
export function AuthCard({
  title,
  error,
  children,
}: {
  title: string;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <Center mih="100vh" p="md">
      <Paper withBorder shadow="sm" p="xl" w="100%" maw={440}>
        <Stack>
          <Title order={1} size="h5" c="dimmed">
            {APP_NAME}
          </Title>
          <Title order={2}>{title}</Title>
          {error ? (
            <Alert color="red" role="alert">
              {error}
            </Alert>
          ) : null}
          {children}
        </Stack>
      </Paper>
    </Center>
  );
}
