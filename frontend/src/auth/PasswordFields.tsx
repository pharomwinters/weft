import { PasswordInput } from "@mantine/core";
import { useState } from "react";

export const MISMATCH = "The passwords do not match.";

export interface NewPassword {
  value: string;
  /** Shows the mismatch message and returns false unless both entries agree. */
  check(): boolean;
  fields: React.ReactNode;
}

/**
 * A new password typed twice. `errors` are the API's messages for the
 * password field (details.password), shown under the first input.
 */
export function useNewPassword(errors: string[], label = "Password"): NewPassword {
  const [value, setValue] = useState("");
  const [again, setAgain] = useState("");
  const [mismatch, setMismatch] = useState(false);

  function check(): boolean {
    const same = value === again;
    setMismatch(!same);
    return same;
  }

  const fields = (
    <>
      <PasswordInput
        label={label}
        description="At least 12 characters."
        autoComplete="new-password"
        required
        value={value}
        onChange={(event) => setValue(event.currentTarget.value)}
        error={errors.length > 0 ? errors.join(" ") : undefined}
      />
      <PasswordInput
        label={`${label} again`}
        autoComplete="new-password"
        required
        value={again}
        onChange={(event) => setAgain(event.currentTarget.value)}
        error={mismatch ? MISMATCH : undefined}
      />
    </>
  );
  return { value, check, fields };
}
