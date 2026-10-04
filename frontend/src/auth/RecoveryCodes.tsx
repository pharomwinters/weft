import { Button, Checkbox, Code, Group, SimpleGrid, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";

import { APP_NAME } from "../constants";
import { copyText } from "../layout/clipboard";

/**
 * The one showing of a user's recovery codes. They live in the parent's
 * component state only, so they are gone once the user moves on.
 */
export default function RecoveryCodes({
  codes,
  onContinue,
}: {
  codes: string[];
  onContinue(): void;
}) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState<boolean | null>(null);
  const text = codes.join("\n");

  useEffect(() => {
    // Leaving now loses the codes for good, so the browser asks first.
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  async function copy() {
    setCopied(await copyText(text));
  }

  function download() {
    const url = URL.createObjectURL(new Blob([text + "\n"], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${APP_NAME.toLowerCase()}-recovery-codes.txt`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return (
    <Stack>
      <Text>
        Each of these codes signs you in once if you lose your authenticator. They are
        shown only now. Keep them somewhere safe.
      </Text>
      <SimpleGrid cols={2} spacing="xs" aria-label="Recovery codes">
        {codes.map((code) => (
          <Code key={code} fz="sm">
            {code}
          </Code>
        ))}
      </SimpleGrid>
      <Group>
        <Button variant="default" onClick={() => void copy()}>
          {copied === null ? "Copy" : copied ? "Copied" : "Select and copy by hand"}
        </Button>
        <Button variant="default" onClick={download}>
          Download
        </Button>
      </Group>
      <Checkbox
        label="I have saved these"
        checked={saved}
        onChange={(event) => setSaved(event.currentTarget.checked)}
      />
      <Button disabled={!saved} onClick={onContinue}>
        Continue
      </Button>
    </Stack>
  );
}
