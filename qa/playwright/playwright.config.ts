import { defineConfig, devices } from '@playwright/test';

/**
 * Fox in the Box — Playwright config.
 *
 * Phase 0 (v0.7.7): rails + one /health spec. Single container on port 8801.
 * Phase 1 (v0.7.8): adds 12 specs covering wizard + endpoints + overlay + retry.
 * Phase 2 (deferred): scales to 4 isolated containers on 8801-8804 with the
 *   `full` matrix shape already wired in this config.
 *
 * Worker / retry policy:
 * - PR-triggered (CI=true, not nightly): 4 workers, 1 retry. Stays under the
 *   5-minute budget per the smoke job's purpose.
 * - Nightly cron (CI=true + PLAYWRIGHT_NIGHTLY=1): 4 workers, 0 retries. A
 *   flaky test on nightly is information — don't paper over it with a retry.
 * - Local (CI unset): 4 workers, 0 retries — fail fast for the developer.
 */

const IS_CI = !!process.env.CI;
const IS_NIGHTLY = process.env.PLAYWRIGHT_NIGHTLY === '1';

export default defineConfig({
  testDir: './tests',
  // Run tests in parallel within and across files.
  fullyParallel: true,
  // Fail the build on test.only — caught CI bugs in past projects.
  forbidOnly: IS_CI,
  workers: 4,
  retries: IS_CI && !IS_NIGHTLY ? 1 : 0,

  reporter: IS_CI
    ? [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]]
    : [['list']],

  use: {
    // Base URL: tests can use page.goto('/health') etc. Override per project
    // for the multi-container Phase 2 shape.
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:8801',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'smoke',
      testDir: './tests/smoke',
      use: { ...devices['Desktop Chrome'] },
    },
    // Phase 1+ projects (matrix shape — no specs yet). Kept commented so the
    // shape is visible to future contributors but doesn't run on Phase 0 CI.
    // {
    //   name: 'chromium',
    //   testDir: './tests/critical',
    //   use: { ...devices['Desktop Chrome'] },
    // },
    // {
    //   name: 'firefox',
    //   testDir: './tests/critical',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   testDir: './tests/critical',
    //   use: { ...devices['Desktop Safari'] },
    // },
  ],

  // Optional: global setup spins up the test container + mock servers.
  // Phase 0: stubbed (the smoke spec hits an already-running container that
  // the CI workflow starts). Phase 1+ will move to an in-test orchestrator.
  // globalSetup: require.resolve('./global-setup'),
  // globalTeardown: require.resolve('./global-teardown'),
});
