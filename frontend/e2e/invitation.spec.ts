import { expect, test } from "@playwright/test";

import { acceptInvitation, admin, shownLink, signIn } from "./helpers";

// The second test needs the link the first one uses up, so they run as a pair.
test.describe.configure({ mode: "serial" });
let usedInvitation = "";

test("owner invites a viewer; viewer joins, enrols, sees the workspace, has no member controls", async ({
  page,
  browser,
}) => {
  await signIn(page, admin());
  await page.getByLabel(/^New workspace/).fill("Team E2E");
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByRole("link", { name: "Team E2E" }).click();
  await expect(page.getByRole("heading", { name: "Team E2E" })).toBeVisible();
  // The owner has the controls.
  await expect(page.getByRole("button", { name: "Delete workspace" })).toBeVisible();

  await page.getByLabel("Invite someone new").selectOption("viewer");
  await page.getByRole("button", { name: "Create invitation link" }).click();
  usedInvitation = await shownLink(page, "invite");

  const invitee = await browser.newContext();
  const preview = await invitee.newPage();
  await preview.goto(usedInvitation);
  await expect(preview.getByText("workspace Team E2E as viewer")).toBeVisible();
  await invitee.close();

  const { page: viewer } = await acceptInvitation(browser, usedInvitation, "viewer@example.com");
  await viewer.getByRole("link", { name: "Team E2E" }).click();
  await expect(viewer.getByRole("heading", { name: "Team E2E" })).toBeVisible();
  await expect(viewer.getByRole("heading", { name: "Members" })).toBeVisible();
  await expect(viewer.getByRole("cell", { name: "viewer@example.com", exact: true })).toBeVisible();
  await expect(viewer.getByRole("button", { name: /Remove/ })).toHaveCount(0);
  await expect(viewer.getByRole("button", { name: "Delete workspace" })).toHaveCount(0);
  await expect(viewer.getByRole("button", { name: "Create invitation link" })).toHaveCount(0);
  await expect(viewer.getByLabel(/^Workspace name/)).toHaveCount(0);
  // Not an admin either.
  await expect(viewer.getByRole("link", { name: "Users" })).toHaveCount(0);

  // The owner now sees the new member.
  await page.reload();
  await expect(page.getByRole("cell", { name: "viewer@example.com", exact: true })).toBeVisible();
});

test("a used invitation link shows the no-longer-valid message", async ({ page }) => {
  expect(usedInvitation).not.toBe("");
  await page.goto(usedInvitation);
  await expect(page.getByRole("alert")).toContainText("This invitation is no longer valid.");
  await expect(page.getByRole("button", { name: "Create account" })).toHaveCount(0);
});
