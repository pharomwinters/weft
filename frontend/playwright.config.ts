import { defineConfig, devices } from "@playwright/test";

// The specs share one server and one database, and later ones build on the
// admin the first creates, so everything runs in order on a single worker.
export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  // A sign-in may have to wait for the next 30-second TOTP step: the server
  // refuses a step it has already accepted for that user.
  timeout: 120_000,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:8010",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "setup",
      testMatch: "setup.spec.ts",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "flows",
      testIgnore: "setup.spec.ts",
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "sh ../scripts/e2e-server.sh",
    url: "http://localhost:8010/api/v1/health",
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: "pipe",
  },
});
