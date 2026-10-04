import { Button, Group, Modal, Text, type ButtonProps } from "@mantine/core";
import { useState } from "react";

/** A button whose action only runs after the user confirms it in a dialog. */
export function ConfirmButton({
  label,
  title,
  message,
  confirmLabel,
  onConfirm,
  ...button
}: {
  label: string;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm(): void;
} & ButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="default" size="xs" {...button} onClick={() => setOpen(true)}>
        {label}
      </Button>
      <Modal opened={open} onClose={() => setOpen(false)} title={title} centered>
        <Text mb="md">{message}</Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            color="red"
            onClick={() => {
              setOpen(false);
              onConfirm();
            }}
          >
            {confirmLabel}
          </Button>
        </Group>
      </Modal>
    </>
  );
}
