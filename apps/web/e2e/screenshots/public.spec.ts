import { test } from '@playwright/test';
import { captureScreen, gotoAndSettle, setLanguage } from '../support/screenshot';
import type { Lang } from '../support/screenshot';
import { PUBLIC_SCREENS } from '../support/screens';

// Screens 1–3 (`docs/SCREENS.md`): signed out. A fresh, cookie-less context per test — the
// default project's `storageState` (a signed-in staff session) would land these on `/` instead
// of the sign-in screen.
test.use({ storageState: { cookies: [], origins: [] } });

for (const screen of PUBLIC_SCREENS) {
  for (const lang of ['az', 'en'] as const) {
    test(`@screenshot ${screen.slug} (${lang})`, async ({ page }) => {
      await gotoAndSettle(page, screen.path);
      await setLanguage(page, lang as Lang);
      await captureScreen(page, screen.slug, lang as Lang);
    });
  }
}
