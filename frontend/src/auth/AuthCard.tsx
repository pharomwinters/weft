import { Alert, Center, Paper, Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

import { APP_NAME, APP_TAGLINE } from "../constants";

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
          <div>
            <Title order={1} size="h4">
              {APP_NAME}
            </Title>
            <Text size="sm" c="dimmed">
              {APP_TAGLINE}
            </Text>
          </div>
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
