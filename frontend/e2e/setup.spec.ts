import { expect, test } from "@playwright/test";

import { admin, createAdmin, enterPassword, field, signIn, signOut } from "./helpers";

test("first run: token → admin → enrol → recovery codes → workspace list", async ({ page }) => {
  const account = await createAdmin(page);
  await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();
  await expect(page.getByText(account.email)).toBeVisible();
  // The first user is an instance admin.
  await expect(page.getByRole("link", { name: "Audit log" })).toBeVisible();
});

test("setup page is gone after the admin exists", async ({ page }) => {
  await page.goto("/setup");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  const status = await page.request.get("/api/v1/setup/status");
  expect(status.status()).toBe(404);
});

test("sign out, sign in with password and TOTP", async ({ page }) => {
  await signIn(page, admin());
  await signOut(page);
  // Signed out for real: the app sends a visitor back to the login page.
  await page.goto("/account");
  await expect(page).toHaveURL(/\/login$/);
});

test("a wrong code shows an error and a recovery code signs in once", async ({ page }) => {
  const account = admin();
  const recoveryCode = account.recoveryCodes[0]!;

  await enterPassword(page, account);
  await page.getByLabel(field.code).fill("000000");
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("alert")).toContainText("That code is not valid.");
  await expect(page).toHaveURL(/\/verify$/);

  await page.getByRole("button", { name: "Use a recovery code instead" }).click();
  await page.getByLabel(/^Recovery code/).fill(recoveryCode);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();
  await signOut(page);

  // The same recovery code a second time is refused.
  await enterPassword(page, account);
  await page.getByRole("button", { name: "Use a recovery code instead" }).click();
  await page.getByLabel(/^Recovery code/).fill(recoveryCode);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("alert")).toContainText("That code is not valid.");
  await expect(page).toHaveURL(/\/verify$/);
});
