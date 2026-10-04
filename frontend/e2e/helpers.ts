import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Browser, type Page } from "@playwright/test";
import * as OTPAuth from "otpauth";

const HERE = dirname(fileURLToPath(import.meta.url));
const BOOTSTRAP_LOG = join(HERE, ".bootstrap.log");
// What earlier tests created on this server run; e2e-server.sh deletes it.
const STATE_FILE = join(HERE, ".state.json");

const STEP_MS = 30_000;

export interface Account {
  email: string;
  password: string;
  secret: string;
  recoveryCodes: string[];
}

interface State {
  admin?: Account;
  /** The last time step each secret's code was generated for. */
  steps: Record<string, number>;
}

function readState(): State {
  if (!existsSync(STATE_FILE)) return { steps: {} };
  return JSON.parse(readFileSync(STATE_FILE, "utf8")) as State;
}

function writeState(state: State): void {
  writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

/** The one-time token the server printed when it started. */
export function setupToken(): string {
  const match = readFileSync(BOOTSTRAP_LOG, "utf8").match(/^Setup token: (\S+)$/m);
  if (!match?.[1]) throw new Error("No setup token in the bootstrap log");
  return match[1];
}

/**
 * A code the server will accept for this secret.
 *
 * The server refuses a time step it has already accepted, so two sign-ins
 * within 30 seconds need codes for different steps. It tolerates one step
 * ahead; beyond that this waits for the clock.
 */
export async function totp(secret: string): Promise<string> {
  const state = readState();
  const now = () => Math.floor(Date.now() / STEP_MS);
  const step = Math.max(now(), (state.steps[secret] ?? 0) + 1);
  while (step > now() + 1) await new Promise((resolve) => setTimeout(resolve, 500));
  state.steps[secret] = step;
  writeState(state);
  return new OTPAuth.TOTP({ secret: OTPAuth.Secret.fromBase32(secret) }).generate({
    timestamp: step * STEP_MS,
  });
}

const field = {
  email: /^Email/,
  password: /^Password( \*)?$/,
  passwordAgain: /^Password again/,
  newPassword: /^New password( \*)?$/,
  newPasswordAgain: /^New password again/,
  code: /^Authentication code/,
};
export { field };

/** On /enrol: read the secret, confirm it, acknowledge the recovery codes. */
export async function enrol(page: Page): Promise<{ secret: string; recoveryCodes: string[] }> {
  await expect(page).toHaveURL(/\/enrol$/);
  const secret = (await page.getByLabel("Secret key").innerText()).trim();
  await page.getByLabel(field.code).fill(await totp(secret));
  await page.getByRole("button", { name: "Confirm" }).click();

  await expect(page.getByRole("heading", { name: "Save your recovery codes" })).toBeVisible();
  const recoveryCodes = await page.getByLabel("Recovery codes").locator("code").allInnerTexts();
  expect(recoveryCodes).toHaveLength(10);
  await expect(page.getByRole("button", { name: "Continue" })).toBeDisabled();
  await page.getByLabel("I have saved these").check();
  await page.getByRole("button", { name: "Continue" }).click();
  return { secret, recoveryCodes };
}

/** First-run setup through the UI. Remembers the admin for later tests. */
export async function createAdmin(page: Page): Promise<Account> {
  const email = "admin@example.com";
  const password = "the e2e admin passphrase";
  await page.goto("/");
  await expect(page).toHaveURL(/\/setup$/);
  await page.getByLabel("Setup token").fill(setupToken());
  await page.getByLabel(field.email).fill(email);
  await page.getByLabel(field.password).fill(password);
  await page.getByLabel(field.passwordAgain).fill(password);
  await page.getByRole("button", { name: "Create admin" }).click();

  const admin = { email, password, ...(await enrol(page)) };
  writeState({ ...readState(), admin });
  return admin;
}

/** The admin an earlier test created on this server. */
export function admin(): Account {
  const account = readState().admin;
  if (!account) throw new Error("The admin has not been created yet (setup.spec.ts runs first)");
  return account;
}

export async function enterPassword(page: Page, account: Pick<Account, "email" | "password">) {
  await page.goto("/login");
  await page.getByLabel(field.email).fill(account.email);
  await page.getByLabel(field.password).fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

export async function signIn(page: Page, account: Account): Promise<void> {
  await enterPassword(page, account);
  await expect(page).toHaveURL(/\/verify$/);
  await page.getByLabel(field.code).fill(await totp(account.secret));
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();
}

export async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

/** The link shown once after creating an invitation or a reset link. */
export async function shownLink(page: Page, kind: "invite" | "reset"): Promise<string> {
  const text = await page.locator("pre", { hasText: `/${kind}/` }).innerText();
  return new URL(text.trim()).pathname;
}

/** Accept an invitation in a fresh browser context and enrol. */
export async function acceptInvitation(
  browser: Browser,
  path: string,
  email: string,
): Promise<{ page: Page; account: Account }> {
  const password = "an invited e2e passphrase";
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(path);
  await page.getByLabel(field.email).fill(email);
  await page.getByLabel(field.password).fill(password);
  await page.getByLabel(field.passwordAgain).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  const account = { email, password, ...(await enrol(page)) };
  await expect(page.getByRole("heading", { name: "Workspaces" })).toBeVisible();
  return { page, account };
}

/** As the signed-in admin: create an instance invitation, return its path. */
export async function inviteToInstance(adminPage: Page): Promise<string> {
  await adminPage.getByRole("link", { name: "Invitations" }).click();
  await adminPage.getByRole("button", { name: "Create invitation link" }).click();
  const path = await shownLink(adminPage, "invite");
  await adminPage.getByRole("button", { name: "Done" }).click();
  return path;
}
