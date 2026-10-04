import { expect, test } from "@playwright/test";

import {
  acceptInvitation,
  admin,
  enterPassword,
  field,
  inviteToInstance,
  shownLink,
  signIn,
  totp,
} from "./helpers";

test("admin creates a reset link; user sets a new password and still needs TOTP", async ({
  page,
  browser,
}) => {
  await signIn(page, admin());
  const invitation = await inviteToInstance(page);
  const { page: userPage, account } = await acceptInvitation(
    browser,
    invitation,
    "forgetful@example.com",
  );
  await userPage.context().close();

  await page.getByRole("link", { name: "Users" }).click();
  await page.getByRole("button", { name: `Create reset link for ${account.email}` }).click();
  const resetPath = await shownLink(page, "reset");

  const context = await browser.newContext();
  const visitor = await context.newPage();
  const newPassword = "a new passphrase after reset";
  await visitor.goto(resetPath);
  await visitor.getByLabel(field.newPassword).fill(newPassword);
  await visitor.getByLabel(field.newPasswordAgain).fill(newPassword);
  await visitor.getByRole("button", { name: "Change password" }).click();
  await expect(visitor.getByRole("heading", { name: "Password changed" })).toBeVisible();

  // The old password no longer works.
  await enterPassword(visitor, account);
  await expect(visitor.getByRole("alert")).toContainText("Incorrect email or password.");

  // The new one does, and the authenticator is still required.
  await enterPassword(visitor, { email: account.email, password: newPassword });
  await expect(visitor).toHaveURL(/\/verify$/);
  await visitor.getByLabel(field.code).fill(await totp(account.secret));
  await visitor.getByRole("button", { name: "Verify" }).click();
  await expect(visitor.getByRole("heading", { name: "Workspaces" })).toBeVisible();

  // The link was single-use.
  const again = await context.newPage();
  await again.goto(resetPath);
  await expect(again.getByRole("alert")).toContainText("This reset link is no longer valid.");
});

test("admin resets a user's 2FA; user must enrol again at next login", async ({
  page,
  browser,
}) => {
  await signIn(page, admin());
  const invitation = await inviteToInstance(page);
  const { page: userPage, account } = await acceptInvitation(
    browser,
    invitation,
    "lostphone@example.com",
  );

  await page.getByRole("link", { name: "Users" }).click();
  await page.getByRole("button", { name: `Reset 2FA for ${account.email}` }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Reset two-factor" }).click();
  const row = page.getByRole("row", { name: new RegExp(account.email) });
  await expect(row.getByText("No 2FA yet")).toBeVisible();

  // The user's open session was ended.
  await userPage.reload();
  await expect(userPage).toHaveURL(/\/login$/);

  // At the next sign-in they are sent to set up a new authenticator.
  await enterPassword(userPage, account);
  await expect(userPage).toHaveURL(/\/enrol$/);
  const newSecret = (await userPage.getByLabel("Secret key").innerText()).trim();
  expect(newSecret).not.toBe(account.secret);
  await userPage.getByLabel(field.code).fill(await totp(newSecret));
  await userPage.getByRole("button", { name: "Confirm" }).click();
  await expect(
    userPage.getByRole("heading", { name: "Save your recovery codes" }),
  ).toBeVisible();
});
