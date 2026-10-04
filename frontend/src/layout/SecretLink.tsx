import { Alert, Button, Code, Group, Stack, Text } from "@mantine/core";
import { useState } from "react";

import { copyText } from "./clipboard";

/**
 * A link the server will never show again (an invitation or a reset link).
 * It lives in the caller's component state only.
 */
export function SecretLink({
  title,
  url,
  note,
  onDismiss,
}: {
  title: string;
  url: string;
  note: string;
  onDismiss(): void;
}) {
  const [copied, setCopied] = useState<boolean | null>(null);

  async function copy() {
    setCopied(await copyText(url));
  }

  return (
    <Alert title={title} color="blue">
      <Stack gap="xs">
        <Text size="sm">{note}</Text>
        <Code block style={{ userSelect: "all" }}>
          {url}
        </Code>
        <Group>
          <Button size="xs" onClick={() => void copy()}>
            {copied === null ? "Copy link" : copied ? "Copied" : "Select and copy by hand"}
          </Button>
          <Button size="xs" variant="default" onClick={onDismiss}>
            Done
          </Button>
        </Group>
      </Stack>
    </Alert>
  );
}
