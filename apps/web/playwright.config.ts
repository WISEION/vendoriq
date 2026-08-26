import { defineConfig, devices } from '@playwright/test';
import { STAFF_STATE } from './e2e/paths';

// Screenshots of all 34 screens × AZ/EN land in docs/screens/ (brief §7.3).
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // The build host ships Chromium preinstalled and forbids `playwright install`
    // (docs/BUILD_BRIEF.md §9), and its build rarely matches the pinned @playwright/test.
    // Point PW_CHROMIUM_PATH at it there. CI installs the matching browser and leaves this
    // unset, so the variable changes nothing in the pipeline.
    launchOptions: process.env.PW_CHROMIUM_PATH
      ? { executablePath: process.env.PW_CHROMIUM_PATH }
      : {},
  },
  projects: [
    // Signs in once and saves the session; every screen is behind a session since phase 1F.
    { name: 'setup', testMatch: /.*\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: STAFF_STATE },
      dependencies: ['setup'],
    },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:5173',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
