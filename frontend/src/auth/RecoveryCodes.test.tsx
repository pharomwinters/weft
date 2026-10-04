import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MantineProvider } from "@mantine/core";
import { describe, expect, it, vi } from "vitest";

import RecoveryCodes from "./RecoveryCodes";

const CODES = Array.from({ length: 10 }, (_, i) => `aaaa-bbbb-cccc-${String(i).padStart(4, "0")}`);

function setup() {
  const onContinue = vi.fn();
  render(
    <MantineProvider>
      <RecoveryCodes codes={CODES} onContinue={onContinue} />
    </MantineProvider>,
  );
  return onContinue;
}

describe("RecoveryCodes", () => {
  it("keeps Continue disabled until 'I have saved these' is ticked", async () => {
    const onContinue = setup();
    for (const code of CODES) expect(screen.getByText(code)).toBeInTheDocument();
    const proceed = screen.getByRole("button", { name: "Continue" });
    expect(proceed).toBeDisabled();
    await userEvent.click(proceed);
    expect(onContinue).not.toHaveBeenCalled();

    await userEvent.click(screen.getByLabelText("I have saved these"));
    expect(proceed).toBeEnabled();
    await userEvent.click(proceed);
    expect(onContinue).toHaveBeenCalledOnce();
  });

  it("offers copy and download of the ten codes", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const blobs: Blob[] = [];
    URL.createObjectURL = vi.fn((blob: Blob) => {
      blobs.push(blob);
      return "blob:codes";
    });
    URL.revokeObjectURL = vi.fn();
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    setup();

    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith(CODES.join("\n"));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Download" }));
    expect(clicked).toHaveBeenCalledOnce();
    expect(await blobs[0]?.text()).toBe(CODES.join("\n") + "\n");
  });
});
