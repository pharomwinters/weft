import { Alert } from "@mantine/core";

import { messageOf } from "../api/client";

/** The server's own message for a refused action (e.g. last_owner). */
export function Failure({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <Alert color="red" role="alert">
      {messageOf(error)}
    </Alert>
  );
}
