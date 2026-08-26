import { test } from '@playwright/test';
import { ADMIN_STATE } from '../paths';
import { captureScreen, gotoAndSettle, setLanguage } from '../support/screenshot';
import type { Lang } from '../support/screenshot';
import { ADMIN_ONLY_SCREENS } from '../support/screens';

// Screen 32 — `admin-users`: the one screen the manager session cannot open without a 403
// (`listUsers` is `admin`-only — see `support/screens.ts`).
test.use({ storageState: ADMIN_STATE });

for (const screen of ADMIN_ONLY_SCREENS) {
  for (const lang of ['az', 'en'] as const) {
    test(`@screenshot ${screen.slug} (${lang})`, async ({ page }) => {
      await gotoAndSettle(page, screen.path);
      await setLanguage(page, lang as Lang);
      await captureScreen(page, screen.slug, lang as Lang);
    });
  }
}
