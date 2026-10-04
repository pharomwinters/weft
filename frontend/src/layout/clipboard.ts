/**
 * Copy to the clipboard; false if the browser will not allow it (the
 * clipboard API only exists on https and localhost).
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
