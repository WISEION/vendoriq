import { expect, test as setup } from '@playwright/test';
import { ADMIN_STATE, STAFF_STATE, VENDOR_STATE } from './paths';

/**
 * Sign in once as the manager and save the session for the rest of the suite.
 *
 * Phase 1F put every screen behind a session, which is why the phase-0 smoke tests began
 * failing: they navigated straight to `/` and landed on the sign-in screen. Logging in per
 * test would pay for the two-step staff flow five times over, so it happens once here and the
 * storage state is reused — the standard Playwright arrangement.
 *
 * The flow itself is the real one, not a shortcut around it: e-mail and password, then the
 * TOTP code. `AUTH_MODE=test` prints that code onto the challenge screen (brief §6), which is
 * the only reason a browser can complete it unattended.
 */
setup('authenticate as the manager', async ({ page }) => {
  await page.goto('/login/staff');

  await page.fill('input[name="email"]', 'manager@vendoriq.test');
  await page.fill('input[name="password"]', 'Manager!2026');
  await page.locator('button[type="submit"]').last().click();

  const totpField = page.locator('input[name="totp-code"]');
  await expect(totpField).toBeVisible();

  // The challenge screen carries the current code. Read it from the page text rather than a
  // label, so this does not depend on the interface language.
  //
  // No trailing `\b`: the rendered text runs the code straight into the next label
  // ("kod: 898924Autentifikator"), where a digit meets a letter and there is no word
  // boundary at all. The sign-in screen shows exactly one six-digit run.
  const body = (await page.locator('body').textContent()) ?? '';
  const code = body.match(/\d{6}/)?.[0];
  expect(code, 'AUTH_MODE=test should print the TOTP code on the challenge screen').toBeTruthy();

  await totpField.fill(code!);
  await page.locator('button[type="submit"]').last().click();

  // The manager lands on the overview; anything else means the session was not established.
  await expect(page.getByRole('heading', { name: 'İcmal', level: 2 })).toBeVisible();

  await page.context().storageState({ path: STAFF_STATE });
});

/**
 * Sign in once as the admin and save the session — the one screen the manager account cannot
 * open (`/admin/users`, gated by `listUsers`, which the manager permission set does not carry;
 * `docs/SCREENS.md`'s "who that admits today" row for `admin-users` is `admin` alone). Every
 * other screenshot uses the manager session; only that one uses this.
 */
setup('authenticate as the admin', async ({ page }) => {
  await page.goto('/login/staff');

  await page.fill('input[name="email"]', 'admin@vendoriq.test');
  await page.fill('input[name="password"]', 'Admin!2026');
  await page.locator('button[type="submit"]').last().click();

  const totpField = page.locator('input[name="totp-code"]');
  await expect(totpField).toBeVisible();

  const body = (await page.locator('body').textContent()) ?? '';
  const code = body.match(/\d{6}/)?.[0];
  expect(code, 'AUTH_MODE=test should print the TOTP code on the challenge screen').toBeTruthy();

  await totpField.fill(code!);
  await page.locator('button[type="submit"]').last().click();

  await expect(page.getByRole('heading', { name: 'İcmal', level: 2 })).toBeVisible();

  await page.context().storageState({ path: ADMIN_STATE });
});

/**
 * Sign in once as the vendor Wesa (`habib.atakisiyev@wesa.az`) and save the session, the same
 * arrangement as the manager above. `AUTH_MODE=test` accepts `000000` unconditionally
 * (`docs/TEST_ACCOUNTS.md`), so the code step needs no scraping — unlike the staff TOTP, which
 * changes every 30 seconds and has to be read off the challenge screen.
 */
setup('authenticate as the vendor (Wesa)', async ({ page }) => {
  await page.goto('/login');

  await page.fill('input[name="email"]', 'habib.atakisiyev@wesa.az');
  await page.locator('button[type="submit"]').last().click();

  const codeField = page.locator('input[name="one-time-code"]');
  await expect(codeField).toBeVisible();
  await codeField.fill('000000');
  await page.locator('button[type="submit"]').last().click();

  // The vendor lands on its own status screen; anything else means the session failed.
  await expect(page.getByRole('heading', { name: 'Müraciət statusu', level: 2 })).toBeVisible();

  await page.context().storageState({ path: VENDOR_STATE });
});
