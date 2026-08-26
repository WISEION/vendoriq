import { test } from '@playwright/test';
import { VENDOR_STATE } from '../paths';
import { captureScreen, gotoAndSettle, setLanguage } from '../support/screenshot';
import type { Lang } from '../support/screenshot';
import { VENDOR_SCREENS } from '../support/screens';

// Screens 4–14 (`docs/SCREENS.md`): the vendor portal, signed in as Wesa.
test.use({ storageState: VENDOR_STATE });

for (const screen of VENDOR_SCREENS) {
  for (const lang of ['az', 'en'] as const) {
    test(`@screenshot ${screen.slug} (${lang})`, async ({ page }) => {
      await gotoAndSettle(page, screen.path);
      await setLanguage(page, lang as Lang);
      await captureScreen(page, screen.slug, lang as Lang);
    });
  }
}
